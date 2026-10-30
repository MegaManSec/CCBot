#!/usr/bin/env python3

# This file is an original work developed by Joshua Rogers<https://joshua.hu/>.
# Licensed under the AGPL-3.0 License. You should have received a copy of the GNU Affero General Public License along with CCBot. If not, see <https://www.gnu.org/licenses/>.

import feedparser
import time
from bs4 import BeautifulSoup
import re
import os
import requests

SLACK_BULLETPOINT = ' \u2022   '
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
RSS_URL = [ "https://www.blogger.com/feeds/8982037438137564684/posts/default?redirect=false" ]
REFRESH_INTERVAL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 30
FEED_END = re.compile(rb"</(feed|rss|rdf:RDF)>\s*\Z")

cached_feeds = {}

# Keep Slack fields within 2000 characters, with a marker for omitted content.
def truncate_slack_message(message):
    if len(message) > 2000:
        marker = "[...truncated...]"
        return message[:2000 - len(marker)] + marker
    return message

# Send a formatted message to a slack webhook, if SLACK_WEBHOOK is configured.
def send_to_slack(message):
    if SLACK_WEBHOOK is None or len(SLACK_WEBHOOK) == 0:
        print(message)
        return

    response = requests.post(SLACK_WEBHOOK, json=message, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()

# Retrieve the RSS feed
def get_rss_entries(rss_url):
    cached_feed = cached_feeds.get(rss_url)
    headers = {"Cache-Control": "max-age=0"}
    if cached_feed and cached_feed["modified"]:
        headers["If-Modified-Since"] = cached_feed["modified"]

    response = requests.get(rss_url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    if response.status_code == 304:
        if cached_feed is None:
            raise ValueError(f"Received 304 without a cached feed: {rss_url}")
        # Replay entries so failed notifications can be retried even if the feed is unchanged.
        return cached_feed["entries"]
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    if not feed.version or not FEED_END.search(response.content):
        raise ValueError(f"Invalid RSS feed: {rss_url}")

    if feed.entries:
        cached_feeds[rss_url] = {
            "modified": response.headers.get("Last-Modified"),
            "entries": feed.entries,
        }
    return feed.entries

# Ensure that the URL is formatted with "https://"
def normalize_url(url):
    return "https" + url[4:] if url[:5] == "http:" else url

# Retrieve multiple RSS feeds
def get_all_rss_entries(rss_urls):
    all_entries = []
    seen_urls = set()

    for rss_url in rss_urls:
        for entry in get_rss_entries(rss_url):
            if not entry.get('link'):
                print(f"Skipping an entry without a link in {rss_url}")
                continue
            url = normalize_url(entry.link)
            if url not in seen_urls:
                all_entries.append(entry)
                seen_urls.add(url)

    return all_entries

# Check if an article contains the word "security"
def contains_security_keyword(article_content):
    return "security" in article_content.lower()

# Format a unix time to readable.
def format_published_time(published_parsed):
    return time.strftime("[%d/%m/%y %H:%M:%S]", published_parsed)

# Ensure that the blog post contains the appropriate tags.
def contains_specified_tags(tags):
    GOT_STABLE = False
    GOT_DESKTOP = False

    for term in tags:
        if not hasattr(term, "term"):
            continue
        if term['term'] in ('Extended Stable updates', 'Stable updates'):
            GOT_STABLE = True
        if term['term'] == 'Desktop Update':
            GOT_DESKTOP = True

    return GOT_STABLE and GOT_DESKTOP

# Match the CVEs posted in the description based on HTML.
# We use two expressions based on previous occurences.
def extract_security_content(description):
    span_pattern = r'<span.*?> {0,1}(Critical|High|Medium|Low) {0,1}.*?<\/span><span.*?>.{0,5}(CVE.*?) {0,1}<\/span>'
    span_match = re.findall(span_pattern, description, re.IGNORECASE)
    if span_match:
        return span_match

    span_pattern = r'\>\] {0,1}(Critical|High|Medium|Low) {0,1}.*?.{0,5}(CVE.*?) {0,1}\.'
    span_match = re.findall(span_pattern, description, re.IGNORECASE)
    if span_match:
        return span_match

    return None

# Match CVEs posted in the post based on the rendered text of the post.
# We first render the HTML's text itself, then match the CVEs, as this is likely more consistent than HTML.
def extract_security_content_from_url(url):
    response = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')
    cve_section = soup.find('div', {'class': 'post-body'})
    if cve_section is None:
        raise ValueError(f"Article has no post body: {url}")
    cve_text = " ".join(cve_section.get_text().split())
    cve_pattern = r' {0,1}(Critical|High|Medium|Low) {0,1}(CVE-\d+-\d+): ([^.]*)\.'
    cve_matches = re.findall(cve_pattern, cve_text)
    return cve_matches

# Parse a single post's details, search for security issues, and log or post to slack.
def process_rss_entry(entry):
    url = normalize_url(entry.link)

    if entry.title.lower() != "stable channel update for desktop":
        if not hasattr(entry, "tags"):
            return
        if not contains_specified_tags(entry.tags):
            return

    article_content = entry.get('summary', entry.get('description', ''))
    formatted_time = format_published_time(entry.published_parsed)
    summary_security_content = extract_security_content(article_content)
    try:
        security_content = extract_security_content_from_url(url)
    except (requests.RequestException, ValueError):
        if not summary_security_content:
            raise
        security_content = None

    security_content = security_content or summary_security_content

    slack_message = f"*{formatted_time}*: URL: {url}\n"
    security_issues = ""

    if security_content:
        for cve in security_content:
            if len(cve) == 3:
                security_issues += f"{SLACK_BULLETPOINT}*[{cve[0]}]*: {cve[1]}: {cve[2]}\n"
            elif len(cve) == 2:
                security_issues += f"{SLACK_BULLETPOINT}*[{cve[0]}]*: {cve[1]}\n"
            else:
                security_issues += f"{SLACK_BULLETPOINT}Something went really wrong and the length of the regex is {len(cve)}! Check the logs..\n"
                print(f"Something went wrong. CVE: {cve}")

    elif contains_security_keyword(article_content):
        security_issues += f"{SLACK_BULLETPOINT}Article contained the word 'security' but no CVEs detected. Someone should double-check..\n"

    if len(security_issues) == 0:
      return

    slack_message = truncate_slack_message(slack_message)
    security_issues = truncate_slack_message(security_issues)

    data = {
        "attachments": [
            {
                "fallback": f"{slack_message}{security_issues}",
                "pretext": f"{slack_message}",
                "color": "#D00000",
                "mrkdwn_in": ["pretext", "fields"],
                "fields": [
                    {
                        "title": "Security Issues",
                        "value": f"{security_issues}",
                        "short": False
                    }
                ]
            }
        ]
    }

    send_to_slack(data)

def main():
    seen_urls = []

    while True:
        try:
            feed_entries = get_all_rss_entries(RSS_URL)
            if not feed_entries:
                raise ValueError("No feed entries to establish a baseline")
            for entry in feed_entries:
                url = normalize_url(entry.link)
                seen_urls.append(url)
            break
        except Exception as e:
            print(f"An error occurred, retrying: {e}")
            time.sleep(REFRESH_INTERVAL_SECONDS)

    while True:
        try:
            feed_entries = get_all_rss_entries(RSS_URL)
            feed_entries.reverse()

            for entry in feed_entries:
                url = normalize_url(entry.link)

                while len(seen_urls) > 500:  # Limit memory use by trimming old entries
                    del seen_urls[0]

                if url in seen_urls:
                    continue

                try:
                    process_rss_entry(entry)
                except Exception as e:
                    print(f"An error occurred processing {url}, retrying: {e}")
                    continue
                seen_urls.append(url)

            time.sleep(REFRESH_INTERVAL_SECONDS)

        except Exception as e:
            print(f"An error occurred, retrying: {e}")
            time.sleep(REFRESH_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
