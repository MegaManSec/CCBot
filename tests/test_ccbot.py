import unittest

from ccbot import ccbot


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
