#!/bin/bash

if [ "$#" -eq 1 ]; then
    SLACK_WEBHOOK_URL=$1
fi

SERVICE_FILE="/etc/systemd/system/ccbot.service"
echo "[Unit]" > $SERVICE_FILE
echo "Description=ccbot Service" >> $SERVICE_FILE
echo "After=network.target" >> $SERVICE_FILE
echo "" >> $SERVICE_FILE
echo "[Service]" >> $SERVICE_FILE
echo "ExecStart=/usr/bin/python3 /usr/local/bin/ccbot.py" >> $SERVICE_FILE
echo "Restart=always" >> $SERVICE_FILE
echo "User=root" >> $SERVICE_FILE
echo "Environment=SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL" >> $SERVICE_FILE
echo "" >> $SERVICE_FILE
echo "[Install]" >> $SERVICE_FILE
echo "WantedBy=default.target" >> $SERVICE_FILE

cp ccbot.py /usr/local/bin/ccbot.py
chmod +x /usr/local/bin/ccbot.py

systemctl daemon-reload
systemctl start ccbot

systemctl enable ccbot
