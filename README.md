# Chrome Checker Bot

Chrome Checker Bot (CCBot), also known as the Chrome/Chromium Vulnerability Checker, is a Python script that monitors the [Chrome Releases blog](https://chromereleases.googleblog.com/) for vulnerabilities announced in Chrome/Chromium.
It polls the blog's Atom feed for Stable desktop releases and checks them for security fixes. If it finds any, it sends a formatted message to Slack through an incoming webhook.

This software was written by [Joshua Rogers](https://joshua.hu/). For more information, see [the blog post](https://joshua.hu/ccbot-chrome-checker-bot-googlechromereleases-chromium-updates).

## Installation

Running CCBot outside Docker requires Python 3.10 or newer.

### Via pip
Install the package into a virtual environment, since many systems no longer allow a system-wide `pip install`:

```bash
python3 -m venv ccbot-venv
ccbot-venv/bin/pip install ccbot-py
SLACK_WEBHOOK_URL='your_slack_webhook_url' ccbot-venv/bin/ccbot
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
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install .
SLACK_WEBHOOK_URL='your_slack_webhook_url' venv/bin/ccbot
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

Each message holds up to 2,000 characters of Security Issues. A longer list is split across several messages, numbered "Security Issues (1/2)", "Security Issues (2/2)" and so on, each with the timestamp and URL. A CVE is never split between messages; a single CVE entry longer than 2,000 characters is cut and ends with `[...truncated...]`.

## Notes
- The script runs until stopped, checking the feed every 10 minutes. A post that fails, for example because it can't be fetched and the feed lists no CVEs for it, or because Slack rejects a message, is retried at the next check. The retry sends only the messages not yet delivered, so a message Slack accepted but whose response was lost can arrive twice. Messages still unsent when the post drops out of the feed, for example because the webhook keeps failing for about a week, are not retried.
- At startup, CCBot records the posts already in the feed and doesn't alert on them, so the first message arrives with the next Stable desktop release. This record and the retries are kept in memory only: after a restart, posts published while CCBot was stopped are never alerted, and messages waiting to be retried are never sent, although earlier messages for the same post may already have been delivered.
- If a post contains the word "security" but no CVEs could be extracted, CCBot still notifies Slack for manual verification, with `Article contained the word 'security' but no CVEs detected. Someone should double-check..`
- CVEs are matched with regular expressions, first against the rendered text of the post, then against the post's HTML in the feed. If Google changes the post format, CVEs may stop being detected; the manual-verification message is the fallback.

## systemd Installation

An installation script for Debian-based systems, [install.sh](https://github.com/MegaManSec/CCBot/blob/main/install.sh), is provided. It needs Python 3.10 or newer (Debian 12 or Ubuntu 22.04 and later) and the `python3-venv` package, and it installs the copy of CCBot in the current directory, so run it as root from the root of a clone:

```bash
sudo apt install python3-venv
git clone https://github.com/MegaManSec/CCBot.git
cd CCBot
sudo ./install.sh "https://hooks.slack.com/services/[...]"
```

The script:

1. Creates (if necessary) a Python virtual environment in `/opt/ccbot`.
2. Installs the package into that virtual environment.
3. Installs, enables and (re)starts a systemd service (`/etc/systemd/system/ccbot.service`) that runs `ccbot` in the background.
4. Configures logging to `/var/log/ccbot.log` and `/var/log/ccbot_error.log`.
5. Sets up log rotation in `/etc/logrotate.d/ccbot`.

When it finishes, it prints `ccbot has been installed, the service is started, and log rotation is set up.` and the paths it used. If creating the virtual environment fails, delete `/opt/ccbot` before running the script again.

The URL argument is optional and sets the service's `SLACK_WEBHOOK_URL`. On a first install without it, the service still starts with an empty webhook, so alerts are only written to `/var/log/ccbot.log`. To set or change the webhook later, run the installer again with the URL, or edit `/etc/systemd/system/ccbot.service` and run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ccbot
```

When reinstalling, the installer rewrites `ccbot.service`:

- Without an argument, it keeps the existing `Environment` and `EnvironmentFile` lines, including the webhook, exactly as they are, as long as `SLACK_WEBHOOK_URL` isn't set in the installer's own environment.
- With a URL argument, or with `SLACK_WEBHOOK_URL` set in its environment (a root shell, `sudo -E`, or `sudo SLACK_WEBHOOK_URL='...' ./install.sh`), it replaces all of those lines with that webhook. An empty value clears it. A plain `sudo` drops variables exported in your shell.
- Any other change to `ccbot.service` is lost, so put other settings in a drop-in with `sudo systemctl edit ccbot`.

## Tests

The tests also run `install.sh`, which isn't in the PyPI package, so they need a clone of this repository and `bash`. After the From source steps, run from the root of the clone:

```bash
venv/bin/python -m unittest discover -s tests
```

## License
This project is licensed under [AGPL-3.0-or-later](https://github.com/MegaManSec/CCBot/blob/main/LICENSE).
