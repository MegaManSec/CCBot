import feedparser
import time
from bs4 import BeautifulSoup
import re
import os
import requests
import json

SLACK_BULLETPOINT = ' \u2022   '
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
RSS_URL = "http://feeds.feedburner.com/GoogleChromeReleases"
REFRESH_INTERVAL_SECONDS = 600

def truncate_slack_message(message):
    while len(message) > 4000:
        longest_word = max(message.split(), key=len)
        message = message.replace(longest_word, "[...truncated...]")
    return message

def send_to_slack(message):
    if SLACK_WEBHOOK is None or len(SLACK_WEBHOOK) == 0:
        print(message)
        return

    message = truncate_slack_message(message)

    headers = {'Content-type': 'application/json'}
    request = requests.post(SLACK_WEBHOOK, headers=headers, data=json.dumps(message))

def get_rss_entries(rss_url):
    feed = feedparser.parse(rss_url)
    return feed.entries

def contains_security_keyword(article_content):
    return "security" in article_content.lower()

def format_published_time(published_parsed):
    return time.strftime("[%d/%m/%y %H:%M:%S]", published_parsed)

def contains_specified_tags(tags):
    specified_terms = {
        'Desktop Update',
        'Stable updates'
    }
    i = 0
    for term in tags:
      if term['term'] == "Desktop Update" or term['term'] == "Stable updates":
        i += 1

    return i == 2 #all(tag['term'] in specified_terms for tag in tags)

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

def extract_security_content_from_url(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    cve_section = soup.find('div', {'class': 'post-body'})
    cve_text = cve_section.get_text()
    cve_pattern = r' {0,1}(Critical|High|Medium|Low) {0,1}(CVE-\d+-\d+): ([^.]*)\.'
    cve_matches = re.findall(cve_pattern, cve_text)
    return cve_matches

def process_rss_entry(entry):
    url = entry.link
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
            elif len(cve) == 1:
                security_issues += f"{SLACK_BULLETPOINT}*[????]*: {cve[0]}\n"
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

    feed_entries = get_rss_entries(RSS_URL)
    for entry in feed_entries:
        url = entry.link
        seen_urls.add(url)

    while True:
        feed_entries = get_rss_entries(RSS_URL)
        feed_entries.reverse()

        for entry in feed_entries:
            url = entry.link

            if url in seen_urls:
                continue

            seen_urls.add(url)
            process_rss_entry(entry)

        time.sleep(REFRESH_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
