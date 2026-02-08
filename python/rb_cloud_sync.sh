#!/bin/bash
cd /opt/stratux/bin/
while(sleep 300); do
python rb_cloud_sync.py -s /var/log -t /tmp -c /boot/firmware/rb/rb-cloud.json;
done