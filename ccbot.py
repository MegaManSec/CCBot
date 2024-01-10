#!/usr/bin/env python3

# This file is an original work developed by Joshua Rogers<https://joshua.hu/>.
# Licensed under the GPL3.0 License.  You should have received a copy of the GNU General Public License along with LDAP-Stalker. If not, see <https://www.gnu.org/licenses/>.

import feedparser
import time
from bs4 import BeautifulSoup
import re
import os
import requests
import json

SLACK_BULLETPOINT = ' \u2022   '
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
RSS_URL = [ "https://feeds.feedburner.com/GoogleChromeReleases", "https://www.blogger.com/feeds/8982037438137564684/posts/default" ]
REFRESH_INTERVAL_SECONDS = 600

# If the message is greater than 4000 characters, replace the longest words (separated by spaces) with [....truncated....] until it fits.
def truncate_slack_message(message):
    while len(message) > 4000:
        longest_word = max(message.split(), key=len)
        message = message.replace(longest_word, "[...truncated...]")
    return message

# Send a formatted message to a slack webhook, if SLACK_WEBHOOK is configured.
def send_to_slack(message):
    if SLACK_WEBHOOK is None or len(SLACK_WEBHOOK) == 0:
        print(message)
        return

    message = truncate_slack_message(message)

    headers = {'Content-type': 'application/json'}
    request = requests.post(SLACK_WEBHOOK, headers=headers, data=json.dumps(message))

# Retrieve the RSS feed
def get_rss_entries(rss_url):
    feed = feedparser.parse(rss_url)
    return feed.entries

# Ensure that the URL is formatted with "https://"
def normalize_url(url):
    return "https" + url[4:] if url[:5] == "http:" else url

# Retrieve multiple RSS feeds
def get_all_rss_entries(rss_urls):
    all_entries = []
    seen_urls = set()

    for rss_url in rss_urls:
        entries = get_rss_entries(rss_url)
        entries = [entry for entry in entries if normalize_url(entry.link) not in seen_urls]
        all_entries.extend(entries)
        seen_urls.update(normalize_url(entry.link) for entry in entries)

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
        if term['term'] in ('Desktop Update'):
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
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    cve_section = soup.find('div', {'class': 'post-body'})
    cve_text = cve_section.get_text()
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
    security_content = extract_security_content_from_url(url)

    if not security_content:
        security_content = extract_security_content(article_content)

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

    data = {
        "attachments": [
            {
                "fallback": f"{slack_message}{security_issues}",
                "pretext": f"{slack_message}",
                "color": "#D00000",
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
    seen_urls = set()

    feed_entries = get_all_rss_entries(RSS_URL)
    for entry in feed_entries:
        url = normalize_url(entry.link)
        seen_urls.add(url)

    while True:
        feed_entries = get_all_rss_entries(RSS_URL)
        feed_entries.reverse()

        for entry in feed_entries:
            url = normalize_url(entry.link)

            if url in seen_urls:
                continue

            seen_urls.add(url)
            process_rss_entry(entry)

        time.sleep(REFRESH_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
