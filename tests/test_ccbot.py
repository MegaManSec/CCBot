import io
import unittest
from unittest.mock import Mock, patch

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


def make_cves(count):
    descriptions = (
        "Use after free in V8",
        "Inappropriate implementation in Picture-in-Picture",
        "Heap buffer overflow in ANGLE",
        "Insufficient validation of untrusted input in Mojo",
        "Out of bounds memory access in WebGPU",
        "Side-channel information leakage in Navigation and Loading",
    )
    severities = ("Critical", "High", "Medium", "Low")
    return [(severities[i % 4], f"CVE-2026-{118300 + i}", descriptions[i % 6]) for i in range(count)]


def format_cves(cves):
    return "".join(f" •   *[{severity}]*: {cve}: {description}\n" for severity, cve, description in cves)


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

    def test_parts_fill_up_to_exactly_the_field_limit(self):
        half = ccbot.SLACK_FIELD_LIMIT // 2
        issues = ["a" * (half - 1) + "\n", "b" * (half - 1) + "\n"]
        self.assertEqual(ccbot.split_slack_message(issues), ["".join(issues)])
        issues[1] = "b" * half + "\n"
        self.assertEqual(ccbot.split_slack_message(issues), issues)


class LongMessageTests(unittest.TestCase):
    header = "*[02/01/24 00:00:00]*: URL: https://example.test/release\n"

    def setUp(self):
        state = patch.dict(ccbot.pending_messages, clear=True)
        state.start()
        self.addCleanup(state.stop)
        last_post = patch.object(ccbot, "last_webhook_post", float("-inf"))
        last_post.start()
        self.addCleanup(last_post.stop)
        sleep = patch.object(ccbot.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        self.entry = feedparser.parse(make_feed("release")).entries[0]

    def send(self, cves):
        with patch.object(ccbot, "extract_security_content_from_url", return_value=cves), \
                patch.object(ccbot, "send_to_slack") as send_to_slack:
            ccbot.process_rss_entry(self.entry)
        return [call.args[0]["attachments"][0] for call in send_to_slack.call_args_list]

    def test_long_lists_are_split_into_numbered_messages(self):
        cves = make_cves(60)
        attachments = self.send(cves)
        values = [attachment["fields"][0]["value"] for attachment in attachments]
        self.assertGreaterEqual(len(attachments), 3)
        self.assertEqual("".join(values), format_cves(cves))
        for number, attachment in enumerate(attachments, 1):
            value = attachment["fields"][0]["value"]
            with self.subTest(part=number):
                self.assertLessEqual(len(value), 2000)
                self.assertTrue(value.endswith("\n"))
                self.assertEqual(attachment["fields"][0]["title"], f"Security Issues ({number}/{len(attachments)})")
                self.assertEqual(attachment["pretext"], self.header)
                self.assertEqual(attachment["fallback"], self.header + value)
        self.assertEqual(ccbot.pending_messages, {})

    def test_short_lists_keep_the_single_message_format(self):
        cves = make_cves(3)
        with patch.object(ccbot, "extract_security_content_from_url", return_value=cves), \
                patch.object(ccbot, "send_to_slack") as send:
            ccbot.process_rss_entry(self.entry)
        issues = format_cves(cves)
        send.assert_called_once_with({
            "attachments": [{
                "fallback": self.header + issues,
                "pretext": self.header,
                "color": "#D00000",
                "mrkdwn_in": ["pretext", "fields"],
                "fields": [{"title": "Security Issues", "value": issues, "short": False}],
            }]
        })

    def test_failed_parts_resume_without_resending_delivered_parts(self):
        cves = make_cves(60)
        with patch.object(ccbot, "extract_security_content_from_url", return_value=cves) as extract, \
                patch.object(ccbot, "send_to_slack", side_effect=[None, requests.HTTPError("rejected"), None, None]) as send:
            with self.assertRaises(requests.HTTPError):
                ccbot.process_rss_entry(self.entry)
            self.assertEqual(len(ccbot.pending_messages["https://example.test/release"]), 2)
            ccbot.process_rss_entry(self.entry)
        titles = [call.args[0]["attachments"][0]["fields"][0]["title"] for call in send.call_args_list]
        self.assertEqual(titles, [f"Security Issues ({number}/3)" for number in (1, 2, 2, 3)])
        extract.assert_called_once()
        self.assertEqual(ccbot.pending_messages, {})

    def test_started_posts_finish_after_their_title_and_tags_change(self):
        with patch.object(ccbot, "extract_security_content_from_url", return_value=make_cves(60)), \
                patch.object(ccbot, "send_to_slack", side_effect=[None, requests.HTTPError("rejected"), None, None]) as send:
            with self.assertRaises(requests.HTTPError):
                ccbot.process_rss_entry(self.entry)
            self.entry["title"] = "Chrome Beta for Desktop Update"
            self.entry["tags"] = [feedparser.FeedParserDict(term="Beta updates")]
            ccbot.process_rss_entry(self.entry)
        titles = [call.args[0]["attachments"][0]["fields"][0]["title"] for call in send.call_args_list]
        self.assertEqual(titles, [f"Security Issues ({number}/3)" for number in (1, 2, 2, 3)])
        self.assertEqual(ccbot.pending_messages, {})

    def test_retries_resend_the_stored_messages_when_the_source_changes(self):
        cves = [("High", f"CVE-2026-{10000 + i}", "Use after free in V8") for i in range(60)]
        self.entry["summary"] = "".join(f"<span>{severity}</span><span>{cve}: {description}.</span>" for severity, cve, description in cves)
        with patch.object(ccbot, "extract_security_content_from_url", side_effect=[requests.ConnectionError("Disconnected"), cves]), \
                patch.object(ccbot, "send_to_slack", side_effect=[None, requests.HTTPError("rejected"), None, None, None]) as send:
            with self.assertRaises(requests.HTTPError):
                ccbot.process_rss_entry(self.entry)
            ccbot.process_rss_entry(self.entry)
        fields = [call.args[0]["attachments"][0]["fields"][0] for call in send.call_args_list]
        delivered = fields[:1] + fields[2:]
        lines = "".join(field["value"] for field in delivered).splitlines()
        self.assertEqual([line.split(": ")[1] for line in lines], [cve for severity, cve, description in cves])
        self.assertEqual([field["title"] for field in delivered], [f"Security Issues ({number}/{len(delivered)})" for number in range(1, len(delivered) + 1)])
        self.assertEqual(ccbot.pending_messages, {})

    def test_entries_with_newlines_stay_in_one_message(self):
        cves = [("High", f"CVE-2026-{10000 + i}", "Use after free in V8") for i in range(37)]
        cves.append(("High", "CVE-2026-20000", "Use after free in V8\nwhen handling crafted JavaScript content"))
        values = [attachment["fields"][0]["value"] for attachment in self.send(cves)]
        self.assertEqual(values, [format_cves(cves[:-1]), format_cves(cves[-1:])])

    def test_overlong_entries_are_truncated_on_their_own(self):
        cves = [
            ("High", "CVE-2026-1111", "Use after free in V8"),
            ("High", "CVE-2026-2222", "x" * 2100),
            ("Low", "CVE-2026-3333", "Type Confusion in V8"),
        ]
        marker = "[...truncated...]"
        values = [attachment["fields"][0]["value"] for attachment in self.send(cves)]
        self.assertEqual(len(values), 3)
        self.assertEqual(values[0], format_cves(cves[:1]))
        self.assertEqual(len(values[1]), 2000)
        self.assertTrue(values[1].endswith(marker))
        self.assertTrue(format_cves(cves[1:2]).startswith(values[1][:-len(marker)]))
        self.assertEqual(values[2], format_cves(cves[2:]))

    def test_webhook_posts_are_paced_across_releases(self):
        clock = [100.0]
        posted = []

        def sleep(seconds):
            clock[0] += seconds

        def post(*args, **kwargs):
            posted.append(clock[0])
            return make_response()

        self.sleep.side_effect = sleep
        entries = feedparser.parse(make_feed("first", "second", "third")).entries
        with patch.object(ccbot, "extract_security_content_from_url", side_effect=[make_cves(60), make_cves(3), make_cves(3)]), \
                patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                patch.object(ccbot.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(ccbot.requests, "post", side_effect=post):
            ccbot.process_rss_entry(entries[0])
            clock[0] += 0.25
            ccbot.process_rss_entry(entries[1])
            clock[0] += 5
            ccbot.process_rss_entry(entries[2])
        self.assertEqual(posted, [100.0, 101.0, 102.0, 103.0, 108.0])
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 1, 0.75])

    def test_printed_alerts_are_not_paced(self):
        entries = feedparser.parse(make_feed("first", "second")).entries
        for webhook in (None, ""):
            with self.subTest(webhook=webhook), \
                    patch.object(ccbot, "extract_security_content_from_url", return_value=make_cves(60)), \
                    patch.object(ccbot, "SLACK_WEBHOOK", webhook), \
                    patch("builtins.print") as log:
                for entry in entries:
                    ccbot.process_rss_entry(entry)
                self.assertEqual(log.call_count, 6)
                self.sleep.assert_not_called()


class SlackDeliveryTests(unittest.TestCase):
    def setUp(self):
        last_post = patch.object(ccbot, "last_webhook_post", float("-inf"))
        last_post.start()
        self.addCleanup(last_post.stop)
        sleep = patch.object(ccbot.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

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

    def test_failed_posts_count_toward_pacing(self):
        clock = [100.0]

        def sleep(seconds):
            clock[0] += seconds

        self.sleep.side_effect = sleep
        with patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                patch.object(ccbot.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(ccbot.requests, "post", side_effect=[requests.ConnectionError("Disconnected"), make_response()]):
            with self.assertRaises(requests.ConnectionError):
                ccbot.send_to_slack({"text": "security update"})
            ccbot.send_to_slack({"text": "security update"})
        self.sleep.assert_called_once_with(1)


class FeedTests(unittest.TestCase):
    def setUp(self):
        cache = patch.dict(ccbot.cached_feeds, clear=True)
        cache.start()
        self.addCleanup(cache.stop)
        state = patch.dict(ccbot.pending_messages, clear=True)
        state.start()
        self.addCleanup(state.stop)
        pacing = patch.object(ccbot, "SLACK_POST_INTERVAL_SECONDS", 0)
        pacing.start()
        self.addCleanup(pacing.stop)

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
            make_response(body=make_feed("release")[:-len("</rss>")]),
            make_response(body=make_feed("release", "older").replace("security update", "security & update", 1)[:-30]),
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

    def test_recoverable_feed_errors_keep_all_entries(self):
        feed = make_feed("release")
        bodies = {
            "bare ampersand": feed.replace("security update", "security & stability update"),
            "control character": feed.replace("security update", "security\x0b update"),
            "undefined entity": feed.replace("security update", "security&nbsp;update"),
            "encoding override": '<?xml version="1.0" encoding="us-ascii"?>' + feed.replace("security update", "security update —"),
        }
        for error, body in bodies.items():
            with self.subTest(error=error), \
                    patch.object(ccbot.requests, "get", return_value=make_response(body=body)):
                entries = ccbot.get_rss_entries("https://example.test/feed")
                self.assertEqual([entry.link for entry in entries], ["https://example.test/release"])

    def test_empty_valid_feeds_are_accepted(self):
        with patch.object(ccbot.requests, "get", return_value=make_response(body=make_feed())):
            self.assertEqual(ccbot.get_rss_entries("https://example.test/feed"), [])

    def test_failed_delivery_retries_on_304_without_duplicate_successes(self):
        feeds = [
            make_response(body=make_feed("historical")),
            make_response(body=make_feed("release", "historical")),
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

    def test_multi_part_alerts_resume_on_304_after_a_failed_part(self):
        cves = make_cves(60)
        feeds = [
            make_response(body=make_feed("historical")),
            make_response(body=make_feed("release", "historical")),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=feeds), \
                patch.object(ccbot.requests, "post", side_effect=[make_response(), make_response(500), make_response(), make_response()]) as post, \
                patch.object(ccbot, "SLACK_WEBHOOK", "https://example.test/webhook"), \
                patch.object(ccbot, "extract_security_content_from_url", return_value=cves) as extract, \
                patch.object(ccbot.time, "sleep", side_effect=[None, StopPolling()]), \
                patch("builtins.print"):
            with self.assertRaises(StopPolling):
                ccbot.main()
        fields = [call.kwargs["json"]["attachments"][0]["fields"][0] for call in post.call_args_list]
        self.assertEqual([field["title"] for field in fields], [f"Security Issues ({number}/3)" for number in (1, 2, 2, 3)])
        self.assertEqual("".join(field["value"] for field in fields[:1] + fields[2:]), format_cves(cves))
        extract.assert_called_once()
        self.assertEqual(ccbot.pending_messages, {})

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

    def test_startup_retries_empty_feed_before_establishing_baseline(self):
        feeds = [
            make_response(body=make_feed(), headers={"Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT"}),
            make_response(body=make_feed("historical")),
            make_response(304),
        ]
        with patch.object(ccbot.requests, "get", side_effect=feeds) as get, \
                patch.object(ccbot, "process_rss_entry") as process, \
                patch.object(ccbot.time, "sleep", side_effect=[None, StopPolling()]), \
                patch("builtins.print"):
            with self.assertRaises(StopPolling):
                ccbot.main()
        process.assert_not_called()
        self.assertNotIn("If-Modified-Since", get.call_args_list[1].kwargs["headers"])


class PollingTests(unittest.TestCase):
    def test_bad_entry_does_not_block_or_duplicate_healthy_notifications(self):
        historical = feedparser.parse(make_feed("historical")).entries
        entries = feedparser.parse(make_feed("healthy", "bad")).entries
        del entries[1]["published_parsed"]
        with patch.object(ccbot, "get_all_rss_entries", side_effect=[historical, entries[:], entries[:]]), \
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
    def test_mixed_html_whitespace_does_not_omit_cves(self):
        html = (
            '<div class="post-body">High CVE-2026-1111: Use after free in V8.<br>'
            'Medium&nbsp;&nbsp;CVE-2026-2222:\n Type confusion in V8.</div>'
        )
        entry = feedparser.parse(make_feed("release")).entries[0]
        with patch.object(ccbot.requests, "get", return_value=make_response(body=html)), \
                patch.object(ccbot, "send_to_slack") as send:
            ccbot.process_rss_entry(entry)
        value = send.call_args.args[0]["attachments"][0]["fields"][0]["value"]
        self.assertIn("CVE-2026-1111", value)
        self.assertIn("CVE-2026-2222", value)
        self.assertIn("Type confusion in V8", value)

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
        for summary in ("A release update", "security update"):
            entry["summary"] = summary
            with self.subTest(summary=summary), \
                    patch.object(ccbot.requests, "get", return_value=make_response(503)), \
                    patch.object(ccbot, "send_to_slack") as send:
                with self.assertRaises(requests.HTTPError):
                    ccbot.process_rss_entry(entry)
                send.assert_not_called()

    def test_security_summary_still_generates_a_manual_check_notification(self):
        entry = feedparser.parse(make_feed("release")).entries[0]
        html = '<div class="post-body">Security fixes are listed in the release notes.</div>'
        with patch.object(ccbot.requests, "get", return_value=make_response(body=html)), \
                patch.object(ccbot, "send_to_slack") as send:
            ccbot.process_rss_entry(entry)
        value = send.call_args.args[0]["attachments"][0]["fields"][0]["value"]
        self.assertIn("no CVEs detected", value)


class OutputTests(unittest.TestCase):
    def test_main_line_buffers_text_stdout_only(self):
        for stdout in (io.TextIOWrapper(io.BytesIO()), io.StringIO(), None):
            with self.subTest(stdout=type(stdout).__name__), \
                    patch.object(ccbot.sys, "stdout", stdout), \
                    patch.object(ccbot, "get_all_rss_entries", return_value=[]), \
                    patch.object(ccbot.time, "sleep", side_effect=StopPolling()), \
                    patch("builtins.print"):
                with self.assertRaises(StopPolling):
                    ccbot.main()
                if isinstance(stdout, io.TextIOWrapper):
                    self.assertTrue(stdout.line_buffering)
