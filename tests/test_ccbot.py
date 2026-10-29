import unittest
from unittest.mock import patch

import requests
import feedparser

from ccbot import ccbot


def make_response(status=200, body="", headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode("utf-8")
    response.headers.update(headers or {})
    return response


def make_feed(*names):
    items = "".join(
        f"<item><title>Stable Channel Update for Desktop</title>"
        f"<link>https://example.test/{name}</link>"
        "<pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>"
        "<description>security update</description></item>"
        for name in names
    )
    return (
        '<rss version="2.0"><channel><title>Chrome</title>'
        '<link>https://example.test/</link><description>Releases</description>'
        f'{items}</channel></rss>'
    )


class StopPolling(BaseException):
    pass


class SlackMessageTests(unittest.TestCase):
    def test_short_messages_are_unchanged(self):
        for message in ("", "A short alert", "x" * 2000):
            with self.subTest(length=len(message)):
                self.assertEqual(ccbot.truncate_slack_message(message), message)

    def test_long_messages_are_bounded_and_marked(self):
        issues = " •   *[High]*: CVE-2026-1234: Use after free in V8\n" * 50
        marker = "[...truncated...]"
        for message in (issues, "x" * 2001, " " * 2001):
            with self.subTest(message=message[:40]):
                result = ccbot.truncate_slack_message(message)
                self.assertLessEqual(len(result), 2000)
                self.assertTrue(result.endswith(marker))
                self.assertTrue(message.startswith(result[:-len(marker)]))


class SlackDeliveryTests(unittest.TestCase):
    def test_rejected_messages_raise_for_retry(self):
        for status in (400, 429, 500):
            with self.subTest(status=status), \
                    patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                    patch.object(ccbot.requests, "post", return_value=make_response(status)):
                with self.assertRaises(requests.HTTPError):
                    ccbot.send_to_slack({"text": "security update"})

    def test_webhook_requests_have_a_timeout(self):
        message = {"text": "security update"}
        with patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                patch.object(ccbot.requests, "post", return_value=make_response()) as post:
            ccbot.send_to_slack(message)
        self.assertEqual(post.call_args.kwargs["json"], message)
        self.assertGreater(post.call_args.kwargs["timeout"], 0)


class FeedTests(unittest.TestCase):
    def setUp(self):
        cache = patch.dict(ccbot.cached_feeds, clear=True)
        cache.start()
        self.addCleanup(cache.stop)

    def test_unchanged_feed_replays_cached_entries(self):
        modified = "Tue, 02 Jan 2024 00:00:00 GMT"
        responses = [
            make_response(body=make_feed("release"), headers={"Last-Modified": modified}),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=responses) as get:
            original = ccbot.get_rss_entries("https://example.test/feed")
            replayed = ccbot.get_rss_entries("https://example.test/feed")
        self.assertEqual([entry.link for entry in replayed], ["https://example.test/release"])
        self.assertEqual(original, replayed)
        self.assertEqual(get.call_args.kwargs["headers"]["If-Modified-Since"], modified)
        self.assertGreater(get.call_args.kwargs["timeout"], 0)

    def test_invalid_feeds_cannot_initialize_the_cache(self):
        responses = [
            make_response(503, "Service Unavailable"),
            make_response(body="<html>Not a feed</html>"),
            make_response(body=make_feed("release")[:-10]),
            make_response(304),
        ]
        for response in responses:
            with self.subTest(status=response.status_code, body=response.text[:30]), \
                    patch.object(ccbot.requests, "get", return_value=response):
                with self.assertRaises((requests.HTTPError, ValueError)):
                    ccbot.get_rss_entries("https://example.test/feed")
                self.assertEqual(ccbot.cached_feeds, {})

    def test_invalid_refresh_keeps_the_last_valid_feed(self):
        responses = [
            make_response(body=make_feed("release")),
            make_response(body="<html>Error</html>"),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=responses):
            original = ccbot.get_rss_entries("https://example.test/feed")
            with self.assertRaises(ValueError):
                ccbot.get_rss_entries("https://example.test/feed")
            self.assertEqual(ccbot.get_rss_entries("https://example.test/feed"), original)

    def test_empty_valid_feeds_are_accepted(self):
        with patch.object(ccbot.requests, "get", return_value=make_response(body=make_feed())):
            self.assertEqual(ccbot.get_rss_entries("https://example.test/feed"), [])

    def test_failed_delivery_retries_on_304_without_duplicate_successes(self):
        feeds = [
            make_response(body=make_feed()),
            make_response(body=make_feed("release")),
            make_response(304),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=feeds), \
                patch.object(ccbot.requests, "post", side_effect=[make_response(500), make_response()]) as post, \
                patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                patch.object(ccbot, "extract_security_content_from_url", return_value=[("High", "CVE-2026-1234", "Use after free")]), \
                patch.object(ccbot.time, "sleep", side_effect=[None, None, StopPolling()]), \
                patch("builtins.print"):
            with self.assertRaises(StopPolling):
                ccbot.main()
        self.assertEqual(post.call_count, 2)

    def test_startup_retries_failed_feed_before_establishing_baseline(self):
        feeds = [
            make_response(503),
            make_response(body=make_feed("historical")),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=feeds), \
                patch.object(ccbot, "process_rss_entry") as process, \
                patch.object(ccbot.time, "sleep", side_effect=[None, StopPolling()]), \
                patch("builtins.print"):
            with self.assertRaises(StopPolling):
                ccbot.main()
        process.assert_not_called()


class PollingTests(unittest.TestCase):
    def test_bad_entry_does_not_block_or_duplicate_healthy_notifications(self):
        entries = feedparser.parse(make_feed("healthy", "bad")).entries
        del entries[1]["published_parsed"]
        with patch.object(ccbot, "get_all_rss_entries", side_effect=[[], entries[:], entries[:]]), \
                patch.object(ccbot, "extract_security_content_from_url", return_value=[("High", "CVE-2026-1234", "Use after free")]), \
                patch.object(ccbot, "send_to_slack") as send, \
                patch.object(ccbot.time, "sleep", side_effect=[None, StopPolling()]), \
                patch("builtins.print") as log:
            with self.assertRaises(StopPolling):
                ccbot.main()
        self.assertEqual(send.call_count, 1)
        self.assertIn("https://example.test/healthy", send.call_args.args[0]["attachments"][0]["pretext"])
        self.assertEqual(log.call_count, 2)

    def test_entries_without_links_do_not_block_feed_aggregation(self):
        entries = feedparser.parse(make_feed("bad", "healthy")).entries
        del entries[0]["link"]
        with patch.object(ccbot, "get_rss_entries", return_value=entries), patch("builtins.print"):
            result = ccbot.get_all_rss_entries(["https://example.test/feed"])
        self.assertEqual([entry.link for entry in result], ["https://example.test/healthy"])


class ArticleTests(unittest.TestCase):
    def test_article_requests_parse_cves_and_have_a_timeout(self):
        html = '<div class="post-body">High CVE-2026-1234: Use after free in V8.</div>'
        with patch.object(ccbot.requests, "get", return_value=make_response(body=html)) as get:
            matches = ccbot.extract_security_content_from_url("https://example.test/release")
        self.assertEqual(matches, [("High", "CVE-2026-1234", "Use after free in V8")])
        self.assertGreater(get.call_args.kwargs["timeout"], 0)

    def test_article_failures_use_cves_from_the_summary(self):
        entry = feedparser.parse(make_feed("release")).entries[0]
        entry["summary"] = '<span>High</span><span>CVE-2026-1234: Use after free in V8.</span>'
        failures = [
            make_response(503, "Service Unavailable"),
            make_response(body="<html>No article body</html>"),
            requests.Timeout("Timed out"),
            requests.ConnectionError("Disconnected"),
        ]
        for failure in failures:
            with self.subTest(failure=str(failure)), \
                    patch.object(ccbot.requests, "get", side_effect=[failure]), \
                    patch.object(ccbot, "send_to_slack") as send:
                ccbot.process_rss_entry(entry)
                self.assertEqual(send.call_count, 1)
                value = send.call_args.args[0]["attachments"][0]["fields"][0]["value"]
                self.assertIn("CVE-2026-1234", value)

    def test_failure_without_useful_summary_is_left_for_retry(self):
        entry = feedparser.parse(make_feed("release")).entries[0]
        entry["summary"] = "A release update"
        with patch.object(ccbot.requests, "get", return_value=make_response(503)), \
                patch.object(ccbot, "send_to_slack") as send:
            with self.assertRaises(requests.HTTPError):
                ccbot.process_rss_entry(entry)
        send.assert_not_called()

    def test_security_summary_still_generates_a_manual_check_notification(self):
        entry = feedparser.parse(make_feed("release")).entries[0]
        with patch.object(ccbot.requests, "get", side_effect=requests.Timeout()), \
                patch.object(ccbot, "send_to_slack") as send:
            ccbot.process_rss_entry(entry)
        value = send.call_args.args[0]["attachments"][0]["fields"][0]["value"]
        self.assertIn("no CVEs detected", value)
