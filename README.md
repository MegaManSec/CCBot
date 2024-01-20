# Chrome Checker Bot

Chrome Checker Bot, also known as Chrome/Chromium Vulnerability Checker. This Python script monitors the Google Chrome release page for any announced vulnerabilities in Chrome/Chromium. It utilizes the Google Chrome Releases RSS feed to fetch the latest updates and checks for security-related content. If security issues are detected, it sends a formatted message to a specified Slack channel using a webhook.

## Prerequisites
- Python 3.x
- `feedparser` library (`pip install feedparser`)
- `beautifulsoup4` library (`pip install beautifulsoup4`)

## Configuration
Before running the script, ensure you set up the following configurations in the script:

- `SLACK_WEBHOOK`: Set your Slack webhook URL as an environment variable.
- `RSS_URL`: Google Chrome Releases RSS feed URL.
- `REFRESH_INTERVAL_SECONDS`: Time interval for checking updates in seconds.

## Usage
1. Install the required libraries:

    ```bash
    pip install feedparser beautifulsoup4
    ```

2. Set up the Slack webhook URL as an environment variable:

    ```bash
    export SLACK_WEBHOOK_URL='your_slack_webhook_url'
    ```

3. Run the script:

    ```bash
    python ccbot.py
    ```

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

## Installation
In addition to running the script manually, a small debian-based installation script [install.sh](install.sh) is provided which when run as root, will install a systemd service to run the script in the background and log the output. The script is installed as /usr/local/bin/ccbot.py, logs are stored in /var/log/ccbot.log and /var/log/ccbot-error.log, and a logrotate configuration file is created in /etc/logrotate.d/ccbot.

An optional first parameter of the installation script can define the _SLACK_WEBHOOK_URL_ environmental variable:

```
$ sudo ./install.sh "https://hooks.slack.com/services/[...]"
ccbot has been installed, the service is started, and log rotation is set up.
```

## License
This project is licensed under [GPL3.0](/LICENSE).
