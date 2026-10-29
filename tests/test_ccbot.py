import unittest
from unittest.mock import patch

import requests

from ccbot import ccbot


def make_response(status=200, body="", headers=None):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode("utf-8")
    response.headers.update(headers or {})
    return response


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
