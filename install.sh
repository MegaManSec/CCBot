#!/bin/bash
set -e

VENV_PATH="/opt/ccbot"

if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi

"$VENV_PATH/bin/pip" install --upgrade pip
"$VENV_PATH/bin/pip" install .

SERVICE_FILE="/etc/systemd/system/ccbot.service"

if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL="$1"
elif [ -z "${SLACK_WEBHOOK_URL+x}" ] && [ -f "$SERVICE_FILE" ]; then
    systemctl daemon-reload
    SLACK_WEBHOOK_URL=$(systemctl show -p Environment --value ccbot | tr ' ' '\n' | sed -n 's/^SLACK_WEBHOOK_URL=//p')
    if [ -z "$SLACK_WEBHOOK_URL" ]; then
        echo "The existing ccbot service has no webhook configured. Pass the webhook URL as an argument, or \"\" to only log alerts." >&2
        exit 1
    fi
fi

cat <<EOL > "$SERVICE_FILE"
[Unit]
Description=ccbot Service
After=network.target

[Service]
Type=simple
ExecStart=$VENV_PATH/bin/ccbot
Restart=always
DynamicUser=yes
Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
StandardOutput=append:/var/log/ccbot.log
StandardError=append:/var/log/ccbot_error.log

[Install]
WantedBy=multi-user.target
EOL

LOGROTATE_FILE="/etc/logrotate.d/ccbot"
cat <<EOL > "$LOGROTATE_FILE"
/var/log/ccbot.log /var/log/ccbot_error.log {
    monthly
    rotate 12
    compress
    missingok
    notifempty
    copytruncate
}
EOL

systemctl daemon-reload
systemctl enable ccbot
systemctl restart ccbot

echo "ccbot has been installed, the service is started, and log rotation is set up."
echo " - Command: $VENV_PATH/bin/ccbot"
echo " - Virtual env: $VENV_PATH"
echo " - Systemd service: /etc/systemd/system/ccbot.service"
echo " - Logs: /var/log/ccbot.log and /var/log/ccbot_error.log"
echo " - Log rotation conf: $LOGROTATE_FILE"
