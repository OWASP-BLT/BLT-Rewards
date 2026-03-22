"""
Unit tests for the pure-Python helpers in src/slack_handler.py.

Run with:
    python -m pytest tests/ -v
or:
    python tests/test_slack_handler.py
"""

import hashlib
import hmac
import sys
import time
import unittest
from pathlib import Path

# Make src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slack_handler import _parse_text, _verify_slack_signature  # noqa: E402


# ---------------------------------------------------------------------------
# _parse_text
# ---------------------------------------------------------------------------

class TestParseText(unittest.TestCase):

    # --- happy-path ---

    def test_plain_at_username_integer(self):
        mention, amount, display = _parse_text("@alice 50")
        self.assertEqual(mention, "@alice")
        self.assertEqual(amount, 50.0)
        self.assertEqual(display, "alice")

    def test_plain_at_username_decimal(self):
        mention, amount, display = _parse_text("@bob 12.5")
        self.assertEqual(mention, "@bob")
        self.assertEqual(amount, 12.5)
        self.assertEqual(display, "bob")

    def test_plain_at_username_with_dots_and_hyphens(self):
        mention, amount, display = _parse_text("@john.doe-dev 100")
        self.assertEqual(mention, "@john.doe-dev")
        self.assertAlmostEqual(amount, 100.0)

    def test_rich_mention_with_display_name(self):
        mention, amount, display = _parse_text("<@U12345678|alice> 75")
        self.assertEqual(mention, "<@U12345678>")
        self.assertEqual(amount, 75.0)
        self.assertEqual(display, "alice")

    def test_rich_mention_without_display_name(self):
        mention, amount, display = _parse_text("<@UABCDEFGH|> 10")
        self.assertEqual(mention, "<@UABCDEFGH>")
        self.assertEqual(amount, 10.0)

    def test_leading_and_trailing_whitespace(self):
        mention, amount, display = _parse_text("  @charlie 33  ")
        self.assertEqual(mention, "@charlie")
        self.assertEqual(amount, 33.0)

    # --- edge cases ---

    def test_zero_amount_is_parsed(self):
        # Parsing succeeds; the handler rejects zero amounts separately.
        mention, amount, _ = _parse_text("@dave 0")
        self.assertEqual(mention, "@dave")
        self.assertEqual(amount, 0.0)

    def test_large_amount(self):
        mention, amount, _ = _parse_text("@whale 999999")
        self.assertEqual(amount, 999999.0)

    # --- failure cases ---

    def test_missing_at_symbol(self):
        mention, amount, display = _parse_text("alice 50")
        self.assertIsNone(mention)
        self.assertIsNone(amount)
        self.assertIsNone(display)

    def test_missing_amount(self):
        mention, amount, display = _parse_text("@alice")
        self.assertIsNone(mention)

    def test_non_numeric_amount(self):
        mention, amount, display = _parse_text("@alice abc")
        self.assertIsNone(mention)

    def test_negative_amount_not_parsed(self):
        # The regex only matches non-negative digits; negative values won't parse.
        mention, amount, display = _parse_text("@alice -10")
        self.assertIsNone(mention)

    def test_empty_string(self):
        mention, amount, display = _parse_text("")
        self.assertIsNone(mention)

    def test_only_whitespace(self):
        mention, amount, display = _parse_text("   ")
        self.assertIsNone(mention)


# ---------------------------------------------------------------------------
# _verify_slack_signature
# ---------------------------------------------------------------------------

def _make_valid_signature(secret: str, body: str, ts: str) -> str:
    """Helper: build a valid Slack signature for the given inputs."""
    sig_base = f"v0:{ts}:{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), sig_base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


class TestVerifySlackSignature(unittest.TestCase):

    SECRET = "test_signing_secret_abc123"

    def _fresh_ts(self) -> str:
        return str(int(time.time()))

    # --- valid ---

    def test_valid_signature_accepted(self):
        body = "text=%40alice+50&user_name=bob"
        ts = self._fresh_ts()
        sig = _make_valid_signature(self.SECRET, body, ts)
        self.assertTrue(_verify_slack_signature(self.SECRET, body, ts, sig))

    def test_valid_empty_body(self):
        body = ""
        ts = self._fresh_ts()
        sig = _make_valid_signature(self.SECRET, body, ts)
        self.assertTrue(_verify_slack_signature(self.SECRET, body, ts, sig))

    # --- invalid ---

    def test_wrong_secret_rejected(self):
        body = "text=%40alice+50"
        ts = self._fresh_ts()
        sig = _make_valid_signature(self.SECRET, body, ts)
        self.assertFalse(_verify_slack_signature("wrong_secret", body, ts, sig))

    def test_tampered_body_rejected(self):
        body = "text=%40alice+50"
        ts = self._fresh_ts()
        sig = _make_valid_signature(self.SECRET, body, ts)
        self.assertFalse(_verify_slack_signature(self.SECRET, "tampered_body", ts, sig))

    def test_old_timestamp_rejected(self):
        body = "text=%40alice+50"
        old_ts = str(int(time.time()) - 301)  # 301 seconds ago
        sig = _make_valid_signature(self.SECRET, body, old_ts)
        self.assertFalse(_verify_slack_signature(self.SECRET, body, old_ts, sig))

    def test_future_timestamp_rejected(self):
        body = "any_body"
        future_ts = str(int(time.time()) + 301)
        sig = _make_valid_signature(self.SECRET, body, future_ts)
        self.assertFalse(_verify_slack_signature(self.SECRET, body, future_ts, sig))

    def test_non_numeric_timestamp_rejected(self):
        body = "any_body"
        self.assertFalse(_verify_slack_signature(self.SECRET, body, "not-a-number", "v0=whatever"))

    def test_wrong_signature_format_rejected(self):
        body = "text=%40alice+50"
        ts = self._fresh_ts()
        self.assertFalse(_verify_slack_signature(self.SECRET, body, ts, "badhash"))


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
