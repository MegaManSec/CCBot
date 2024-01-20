#!/bin/bash
set -e

pip3 install feedparser beautifulsoup4 requests


if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL="$1"
fi

cp ccbot.py /usr/local/bin/ccbot.py
chmod +x /usr/local/bin/ccbot.py
chown root:root /usr/local/bin/ccbot.py

# Step 1: Create a service file for ccbot
SERVICE_FILE="/etc/systemd/system/ccbot.service"

cat <<EOL > $SERVICE_FILE
[Unit]
Description=ccbot Service
After=network.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/ccbot.py
Restart=always
DynamicUser=yes
Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
StandardOutput=append:/var/log/ccbot.log
StandardError=append:/var/log/ccbot_error.log

[Install]
WantedBy=default.target
EOL

# Step 3: Create a logrotate configuration file for ccbot
LOGROTATE_FILE="/etc/logrotate.d/ccbot"
cat <<EOL > $LOGROTATE_FILE
/var/log/ccbot.log /var/log/ccbot_error.log {
    monthly
    rotate 12
    compress
    missingok
    notifempty
    copytruncate
}
EOL

# Step 4: Reload systemd and start the ccbot service
systemctl daemon-reload
systemctl start ccbot

# Step 5: Enable the service to start at boot
systemctl enable ccbot

echo "ccbot has been installed, the service is started, and log rotation is set up."
echo "ccbot has been installed in /usr/local/bin/ccbot.py, and a service has been installed in /etc/systemd/system/ccbot.service. The service is started and logging to /var/log/ccbot.log and /var/log/ccbot_error.log, and log rotation is set up in $LOGROTATE_FILE."
