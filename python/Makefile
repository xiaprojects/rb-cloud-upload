export STRATUX_HOME := /opt/stratux

install: rb_cloud_sync.py
	mkdir -p $(STRATUX_HOME)/bin

	# binaries
	cp -f rb_cloud_sync.py $(STRATUX_HOME)/bin/
	cp -f rb_cloud_sync.sh $(STRATUX_HOME)/bin/
	chmod 755 $(STRATUX_HOME)/bin/rb_cloud_sync.sh
	test -f $(STRATUX_HOME)/www/settings/rb-cloud.json || cp -f rb-cloud.json $(STRATUX_HOME)/www/settings
	# version
	cp -f cloud.version $(STRATUX_HOME)
	cp rb_cloud_sync.service /lib/systemd/system
	systemctl daemon-reload
	systemctl enable rb_cloud_sync.service
