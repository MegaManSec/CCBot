# Chrome Checker Bot

Chrome Checker Bot, also known as Chrome/Chromium Vulnerability Checker. This Python script monitors the Google Chrome release page for any announced vulnerabilities in Chrome/Chromium.
It utilizes the Google Chrome Releases RSS feed to fetch the latest updates and checks for security-related content. If security issues are detected, it sends a formatted message to a specified Slack channel using a webhook.

## Prerequisites
- Python 3.x
- `feedparser` library (`pip install feedparser`)
- `beautifulsoup4` library (`pip install beautifulsoup4`)
- `requests` library (`pip install requests`)

## Configuration
Before running the script, ensure you set up the following configurations in the script:

- `SLACK_WEBHOOK`: Set your Slack webhook URL as an environment variable.
- `RSS_URL`: Google Chrome Releases RSS feed URL.
- `REFRESH_INTERVAL_SECONDS`: Time interval for checking updates in seconds.

## Functionality

The script performs the following tasks:

1. Fetches the latest entries from the Google Chrome Releases RSS feed.
2. Filters entries based on specified tags (`Desktop Update`, `Stable updates`).
3. Extracts security-related content from the entry's description or the linked URL.
4. Formats and sends a Slack message if security issues are detected.

## Slack Message Format
The Slack message includes the following information for each security issue:

- **Timestamp**: Time of the release.
- **URL**: Link to the release details.
- **Security Issues**: List of security issues, including severity, CVE number, and description.

## Notes
- The script runs indefinitely, periodically checking for updates based on the refresh interval.
- If a security-related article is found without specific CVEs, it still notifies Slack for manual verification.
- The script employs regex patterns for extracting security content, adapting to potential variations in the HTML structure.

## Manual Usage

You can run the script in your terminal with the following instructions.

### Usage
1. Set up a Python virtual environment and install the required libraries:

    ```bash
    python3 -m venv .
    ./bin/pip install --upgrade pip
    ./bin/pip install -r requirements.txt
    ```

2. Set up the Slack webhook URL as an environment variable:

    ```bash
    export SLACK_WEBHOOK_URL='your_slack_webhook_url'
    ```

3. Run the script:

    ```bash
    ./bin/python ccbot.py
    ```
## Installation

A Debian-based installation script, [install.sh](install.sh), is provided. When run as root, this script:

1. Creates (if necessary) a Python virtual environment in `/opt/ccbot`.
2. Installs the required packages into that virtual environment.
3. Copies **ccbot.py** to `/usr/local/bin/ccbot.py`.
4. Installs and enables a systemd service (`/etc/systemd/system/ccbot.service`) that runs **ccbot** in the background.
5. Configures logging to `/var/log/ccbot.log` and `/var/log/ccbot_error.log`.
6. Sets up log rotation in `/etc/logrotate.d/ccbot`.

You may optionally pass a single argument to `install.sh` to define the `SLACK_WEBHOOK_URL` environment variable used by the script:

```bash
sudo ./install.sh "https://hooks.slack.com/services/[...]"
ccbot has been installed, the service is started, and log rotation is set up.
```

If you don’t provide a URL, you can manually edit /etc/systemd/system/ccbot.service later to set or change the webhook URL.

## License
This project is licensed under [GPL3.0](/LICENSE).
