# Chrome Checker Bot

Chrome Checker Bot (CCBot), also known as the Chrome/Chromium Vulnerability Checker, is a Python script that monitors the [Chrome Releases blog](https://chromereleases.googleblog.com/) for vulnerabilities announced in Chrome/Chromium.
It polls the blog's Atom feed for Stable desktop releases and checks them for security fixes. If it finds any, it sends a formatted message to Slack through an incoming webhook.

This software was written by [Joshua Rogers](https://joshua.hu/). For more information, see [the blog post](https://joshua.hu/ccbot-chrome-checker-bot-googlechromereleases-chromium-updates).

## Installation

### Via pip
```bash
pip install ccbot-py
```

### Via Docker (Docker Hub)
```bash
docker run -e SLACK_WEBHOOK_URL='your_slack_webhook_url' megamansec/ccbot
```

### Via Docker (GHCR)
```bash
docker run -e SLACK_WEBHOOK_URL='your_slack_webhook_url' ghcr.io/megamansec/ccbot
```

### From source
```bash
git clone https://github.com/MegaManSec/CCBot.git
cd CCBot
pip install .
ccbot
```

## Configuration
CCBot reads one setting from the environment:

- `SLACK_WEBHOOK_URL`: Your Slack incoming webhook URL, read at startup. If it is unset or empty, CCBot prints each alert to standard output instead of sending it.

The feed URL (`RSS_URL`) and the 10-minute refresh interval (`REFRESH_INTERVAL_SECONDS`) are fixed in `ccbot/ccbot.py`. CCBot reads Blogger's own Atom feed with `redirect=false`, because the FeedBurner copy it otherwise redirects to is served stale.

## Functionality

The script performs the following tasks:

1. Fetches the latest entries from the Chrome Releases Atom feed.
2. Keeps only Stable desktop release posts: entries titled "Stable Channel Update for Desktop", or tagged `Desktop Update` together with `Stable updates` or `Extended Stable updates`.
3. Fetches each new post and extracts its CVEs from the post's text. If the post can't be fetched or lists no CVEs, it falls back to the post's HTML in the feed.
4. Sends a Slack message if CVEs are found, or if the post mentions "security" but no CVEs could be extracted.

## Slack Message Format
For each release, CCBot sends a Slack attachment with a red bar:

- **Timestamp**: When the post was published, in UTC, as `[DD/MM/YY HH:MM:SS]`.
- **URL**: Link to the release post.
- **Security Issues**: One line per CVE, with its severity, CVE ID and description.

Each message holds up to 2,000 characters of Security Issues. A longer list is split across several messages, numbered "Security Issues (1/2)", "Security Issues (2/2)" and so on, each with the timestamp and URL. A CVE is never split between messages.

## Notes
- The script runs until stopped, checking the feed every 10 minutes. A post that fails, for example because it can't be fetched and the feed lists no CVEs for it, or because Slack rejects a message, is retried at the next check, without resending the messages already delivered.
- At startup, CCBot records the posts already in the feed and doesn't alert on them, so the first message arrives with the next Stable desktop release. This record is kept in memory only: after a restart, posts published while CCBot was stopped, and posts waiting to be retried, are never alerted.
- If a post contains the word "security" but no CVEs could be extracted, CCBot still notifies Slack for manual verification, with `Article contained the word 'security' but no CVEs detected. Someone should double-check..`
- CVEs are matched with regular expressions, first against the rendered text of the post, then against the post's HTML in the feed. If Google changes the post format, CVEs may stop being detected; the manual-verification message is the fallback.

## Manual Usage

You can run the script in your terminal with the following instructions.

1. Set up a Python virtual environment and install the package:

    ```bash
    python3 -m venv venv
    venv/bin/pip install --upgrade pip
    venv/bin/pip install .
    ```

2. Set up the Slack webhook URL as an environment variable:

    ```bash
    export SLACK_WEBHOOK_URL='your_slack_webhook_url'
    ```

3. Run the script:

    ```bash
    venv/bin/ccbot
    ```

## Systemd Installation

A Debian-based installation script, [install.sh](https://github.com/MegaManSec/CCBot/blob/main/install.sh), is provided. When run as root, this script:

1. Creates (if necessary) a Python virtual environment in `/opt/ccbot`.
2. Installs the package into that virtual environment.
3. Installs and enables a systemd service (`/etc/systemd/system/ccbot.service`) that runs **ccbot** in the background.
4. Configures logging to `/var/log/ccbot.log` and `/var/log/ccbot_error.log`.
5. Sets up log rotation in `/etc/logrotate.d/ccbot`.

You may optionally pass a single argument to `install.sh` to define the `SLACK_WEBHOOK_URL` environment variable used by the script:

```bash
sudo ./install.sh "https://hooks.slack.com/services/[...]"
ccbot has been installed, the service is started, and log rotation is set up.
```

If you don't provide a URL, you can manually edit /etc/systemd/system/ccbot.service later to set or change the webhook URL.
When reinstalling without an argument, the installer keeps the existing service's `Environment` and `EnvironmentFile` lines, including the webhook, exactly as they are.
To change the webhook, pass the new URL as the argument: `sudo` resets the environment, so an exported `SLACK_WEBHOOK_URL` does not reach the installer.
The installer restarts the service to apply updated code and configuration.

## Tests

With the package installed, run the regression tests with:

```bash
python -m unittest discover -s tests
```

## License
This project is licensed under [AGPL-3.0-or-later](https://github.com/MegaManSec/CCBot/blob/main/LICENSE).
