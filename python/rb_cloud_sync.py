#!/usr/bin/env python3
"""
SQLite File Sync Uploader
Synchronizes local SQLite files to remote server via HTTP upload
"""

import os
import sys
import glob
import zipfile
import requests
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class SQLiteSyncUploader:
    def __init__(self, authorization: str, device_id: str, source_folder: str, temp_folder: str, 
                 base_url: str, verbose: bool = False):
        """
        Initialize the SQLite sync uploader
        
        Args:
            device_id: Device identifier
            source_folder: Folder containing *.sqlite files
            temp_folder: Temporary folder for ZIP files
            base_url: Base URL of the upload server
            verbose: Enable verbose logging
        """
        self.authorization = authorization
        self.device_id = device_id
        self.source_folder = Path(source_folder).resolve()
        self.temp_folder = Path(temp_folder).resolve()
        self.base_url = base_url.rstrip('/')
        self.verbose = verbose
        
        # Create folders if they don't exist
        self.source_folder.mkdir(parents=True, exist_ok=True)
        self.temp_folder.mkdir(parents=True, exist_ok=True)
        
        self.log(f"Authorization: {self.authorization}")
        self.log(f"Device ID: {self.device_id}")
        self.log(f"Source folder: {self.source_folder}")
        self.log(f"Temp folder: {self.temp_folder}")
        self.log(f"Base URL: {self.base_url}")
    
    def log(self, message: str, force: bool = False):
        """Print log message if verbose mode is enabled"""
        if self.verbose or force:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")
    
    def fetch_remote_files(self) -> Dict[str, Dict]:
        """
        Fetch list of files already uploaded to server
        
        Returns:
            Dictionary with filename as key and file info as value
        """
        url = f"{self.base_url}/list_files.php"
        params = {'deviceId': self.device_id,'Authorization': self.authorization}
        
        self.log(f"Fetching remote file list from: {url}")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            self.log(response.text)
            data = response.json()

            # Build a dictionary indexed by filename
            remote_files = {}
            files_list = data
            
            for file_info in files_list:
                    filename = file_info.get('name', file_info.get('path', ''))
                    # Extract just the filename if path is provided
                    filename = os.path.basename(filename)
                    remote_files[filename] = {
                        'size': file_info.get('size', 0),
                        'modified': file_info.get('modified', ''),
                        'path': file_info.get('path', '')
                    }
            
            self.log(f"Found {len(remote_files)} remote files")
            return remote_files
            
        except requests.RequestException as e:
            self.log(f"Error fetching remote files: {e}", force=True)
            return {}
        except json.JSONDecodeError as e:
            self.log(f"Error parsing JSON response: {e}", force=True)
            return {}
    
    def get_local_sqlite_files(self) -> List[Path]:
        """
        Get list of all *.sqlite files in source folder
        
        Returns:
            List of Path objects for SQLite files
        """
        patterns = ['*.sqlite', '*.sqlite3', '*.db']
        sqlite_files = []
        
        for pattern in patterns:
            sqlite_files.extend(self.source_folder.glob(pattern))
        
        sqlite_files = sorted(set(sqlite_files))  # Remove duplicates and sort
        self.log(f"Found {len(sqlite_files)} local SQLite files")
        
        return sqlite_files
    
    def should_upload(self, local_file: Path, remote_files: Dict[str, Dict]) -> bool:
        """
        Determine if local file should be uploaded
        
        Args:
            local_file: Path to local file
            remote_files: Dictionary of remote files
        
        Returns:
            True if file should be uploaded, False otherwise
        """
        filename = local_file.name
        local_size = local_file.stat().st_size
        
        if filename not in remote_files:
            self.log(f"  → File not on server, will upload")
            return True
        
        remote_size = remote_files[filename]['size']
        
        if local_size > remote_size:
            self.log(f"  → Local file larger ({local_size} > {remote_size} bytes), will upload")
            return True
        
        self.log(f"  → File up to date (local: {local_size}, remote: {remote_size} bytes)")
        return False
    
    def create_zip(self, sqlite_file: Path) -> Optional[Path]:
        """
        Create ZIP archive of SQLite file
        
        Args:
            sqlite_file: Path to SQLite file to compress
        
        Returns:
            Path to created ZIP file, or None on error
        """
        zip_filename = f"{sqlite_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = self.temp_folder / zip_filename
        
        try:
            self.log(f"  Creating ZIP: {zip_filename}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add file to ZIP with just the filename (no path)
                zipf.write(sqlite_file, arcname=sqlite_file.name)
            
            zip_size = zip_path.stat().st_size
            original_size = sqlite_file.stat().st_size
            compression_ratio = (1 - zip_size / original_size) * 100 if original_size > 0 else 0
            
            self.log(f"  ZIP created: {zip_size} bytes ({compression_ratio:.1f}% compression)")
            return zip_path
            
        except Exception as e:
            self.log(f"  Error creating ZIP: {e}", force=True)
            return None
    
    def upload_file(self, zip_file: Path) -> bool:
        """
        Upload ZIP file to server
        
        Args:
            zip_file: Path to ZIP file to upload
        
        Returns:
            True if upload successful, False otherwise
        """
        url = f"{self.base_url}/upload_and_extract.php"
        params = {'deviceId': self.device_id,'Authorization': self.authorization}

        
        try:
            self.log(f"  Uploading to: {url}")
            
            with open(zip_file, 'rb') as f:
                files = {'file': (zip_file.name, f, 'application/zip')}
                data = {'deviceId': self.device_id}
                
                response = requests.post(url, params=params, files=files, data=data, timeout=300)
                response.raise_for_status()
                
                result = response.json()
                
                if result.get('success', False):
                    self.log(f"  ✓ Upload successful: {result.get('message', '')}")
                    self.log(f"    Files extracted: {result.get('files_extracted', 'N/A')}")
                    return True
                else:
                    self.log(f"  ✗ Upload failed: {result.get('error', 'Unknown error')}", force=True)
                    return False
                    
        except requests.RequestException as e:
            self.log(f"  ✗ Upload error: {e}", force=True)
            return False
        except json.JSONDecodeError as e:
            self.log(f"  ✗ Error parsing response: {e}", force=True)
            return False
    
    def cleanup_temp_file(self, zip_file: Path):
        """Remove temporary ZIP file"""
        try:
            if zip_file.exists():
                zip_file.unlink()
                self.log(f"  Cleaned up temp file: {zip_file.name}")
        except Exception as e:
            self.log(f"  Warning: Could not delete temp file: {e}")
    
    def sync(self, cleanup: bool = True) -> Dict[str, int]:
        """
        Perform synchronization of SQLite files
        
        Args:
            cleanup: Delete temporary ZIP files after upload
        
        Returns:
            Dictionary with statistics (uploaded, skipped, failed)
        """
        stats = {'uploaded': 0, 'skipped': 0, 'failed': 0, 'total': 0}
        
        self.log("=" * 70, force=True)
        self.log("Starting synchronization", force=True)
        self.log("=" * 70, force=True)
        
        # Fetch remote file list
        remote_files = self.fetch_remote_files()
        
        # Get local SQLite files
        local_files = self.get_local_sqlite_files()
        stats['total'] = len(local_files)
        
        if not local_files:
            self.log("No SQLite files found in source folder", force=True)
            return stats
        
        # Process each file
        for idx, sqlite_file in enumerate(local_files, 1):
            self.log(f"\n[{idx}/{stats['total']}] Processing: {sqlite_file.name}", force=True)
            
            # Check if upload is needed
            if not self.should_upload(sqlite_file, remote_files):
                stats['skipped'] += 1
                continue
            
            # Create ZIP
            zip_file = self.create_zip(sqlite_file)
            if not zip_file:
                stats['failed'] += 1
                continue
            
            # Upload
            if self.upload_file(zip_file):
                stats['uploaded'] += 1
            else:
                stats['failed'] += 1
            
            # Cleanup
            if cleanup:
                self.cleanup_temp_file(zip_file)
        
        # Print summary
        self.log("\n" + "=" * 70, force=True)
        self.log("Synchronization complete", force=True)
        self.log("=" * 70, force=True)
        self.log(f"Total files: {stats['total']}", force=True)
        self.log(f"Uploaded: {stats['uploaded']}", force=True)
        self.log(f"Skipped: {stats['skipped']}", force=True)
        self.log(f"Failed: {stats['failed']}", force=True)
        
        return stats


def load_config_file(config_path: str) -> Dict:
    """
    Load configuration from JSON file
    
    Args:
        config_path: Path to JSON configuration file
    
    Returns:
        Dictionary with configuration values
    """
    try:
        config_file = Path(config_path).resolve()
        if not config_file.exists():
            print(f"Error: Configuration file not found: {config_file}", file=sys.stderr)
            sys.exit(1)
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        return config
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Could not read configuration file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Synchronize SQLite files to remote server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --config config.json --source /data/logs --temp /tmp/upload
  %(prog)s -c config.json -s ./logs -t ./temp -v
        """
    )
    
    parser.add_argument('-c', '--config', required=True,
                        help='Path to JSON configuration file (contains device_id, base_url, authorization)')
    parser.add_argument('-s', '--source', required=True,
                        help='Source folder containing *.sqlite files')
    parser.add_argument('-t', '--temp', required=True,
                        help='Temporary folder for ZIP files')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--keep-temp', action='store_true',
                        help='Keep temporary ZIP files after upload')
    
    # Optional command-line overrides (for backward compatibility)
    parser.add_argument('-a', '--authorization',
                        help='Authorization (overrides config file value)')
    parser.add_argument('-d', '--device-id',
                        help='Device identifier (overrides config file value)')
    parser.add_argument('-u', '--url',
                        help='Base URL of upload server (overrides config file value)')
    
    args = parser.parse_args()
    
    # Load configuration from file
    config = load_config_file(args.config)
    
    # Extract values from config, use command-line overrides if provided
    authorization = args.authorization or config.get('authorization')
    device_id = args.device_id or config.get('device_id')
    base_url = args.url or config.get('base_url')
    
    # Validate required configuration values
    if not authorization:
        print("Error: 'authorization' not provided in config file or command line", file=sys.stderr)
        sys.exit(1)
    if not device_id:
        print("Error: 'device_id' not provided in config file or command line", file=sys.stderr)
        sys.exit(1)
    if not base_url:
        print("Error: 'base_url' not provided in config file or command line", file=sys.stderr)
        sys.exit(1)
    
    # Create uploader instance
    uploader = SQLiteSyncUploader(
        authorization=authorization,
        device_id=device_id,
        source_folder=args.source,
        temp_folder=args.temp,
        base_url=base_url,
        verbose=args.verbose
    )
    
    # Perform sync
    stats = uploader.sync(cleanup=not args.keep_temp)
    
    # Exit with error code if any failures
    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
