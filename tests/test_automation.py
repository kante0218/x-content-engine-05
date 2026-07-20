from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import content_guard
import generate_draft
import pipeline
import post_tweet
import preflight


class AutomationTests(unittest.TestCase):
    def test_https_catalog_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "products.json"
            path.write_text(json.dumps({"products": [{"name": "ok", "link": "https://example.com/a"}]}))
            with patch.object(generate_draft, "PRODUCTS", path):
                self.assertEqual(len(generate_draft.load_products()), 1)
            path.write_text(json.dumps({"products": [{"name": "bad", "link": "http://example.com/a"}]}))
            with patch.object(generate_draft, "PRODUCTS", path):
                with self.assertRaises(ValueError):
                    generate_draft.load_products()

    def test_affiliate_daily_cap_counts_pending_and_posted(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / "pending").mkdir(); (base / "posted").mkdir()
            today = generate_draft.dt.datetime.now().strftime("%Y%m%d")
            (base / "pending" / f"{today}_120000_theme_aff.md").write_text("aff: https://x")
            with patch.object(generate_draft, "PENDING", base / "pending"), patch.object(generate_draft, "POSTED", base / "posted"):
                self.assertFalse(generate_draft.affiliate_allowed_today(1))

    def test_pr_format_and_paid_partnership_payload(self):
        text = pipeline.with_affiliate_disclosure("本文", "https://example.com/a")
        self.assertTrue(text.startswith("【PR】\n"))
        self.assertIn("広告リンクを含みます", text)
        with self.assertRaises(ValueError):
            pipeline.with_affiliate_disclosure("本文", "http://example.com/a")
        response = MagicMock(status_code=201)
        response.json.return_value = {"data": {"id": "1"}}
        with patch.object(post_tweet, "OAuth1Session") as session_cls, patch.dict(os.environ, {
            "X_CONSUMER_KEY": "a", "X_CONSUMER_SECRET": "b", "X_ACCESS_TOKEN": "c", "X_ACCESS_TOKEN_SECRET": "d"
        }, clear=False):
            session_cls.return_value.post.return_value = response
            post_tweet.post(text, paid_partnership=True)
            payload = session_cls.return_value.post.call_args.kwargs["json"]
            self.assertIs(payload["paid_partnership"], True)

    def test_organic_payload_omits_paid_partnership(self):
        response = MagicMock(status_code=201); response.json.return_value = {"data": {"id": "1"}}
        with patch.object(post_tweet, "OAuth1Session") as session_cls, patch.dict(os.environ, {
            "X_CONSUMER_KEY": "a", "X_CONSUMER_SECRET": "b", "X_ACCESS_TOKEN": "c", "X_ACCESS_TOKEN_SECRET": "d"
        }, clear=False):
            session_cls.return_value.post.return_value = response
            post_tweet.post("organic")
            self.assertNotIn("paid_partnership", session_cls.return_value.post.call_args.kwargs["json"])

    def test_exact_and_near_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            posted = Path(temp); (posted / "one.md").write_text("猫との暮らしは毎日たのしいです")
            self.assertTrue(content_guard.find_duplicate("猫との暮らしは毎日たのしいです", posted)[0])
            self.assertTrue(content_guard.find_duplicate("猫との暮らしは毎日たのしいです！", posted)[0])

    def test_transient_statuses_are_deferred(self):
        for status in (403, 429, 500, 502, 503, 504):
            self.assertTrue(pipeline.is_deferred_error(RuntimeError(f"status={status}")))
        self.assertFalse(pipeline.is_deferred_error(RuntimeError("status=400")))

    def test_preflight_rejects_wrong_handle(self):
        response = MagicMock(status_code=200); response.json.return_value = {"data": {"username": "wrong"}}
        with patch.object(preflight, "OAuth1Session") as session_cls, patch.dict(os.environ, {
            "X_CONSUMER_KEY": "a", "X_CONSUMER_SECRET": "b", "X_ACCESS_TOKEN": "c", "X_ACCESS_TOKEN_SECRET": "d", "X_HANDLE": "expected"
        }, clear=False):
            session_cls.return_value.get.return_value = response
            with self.assertRaises(RuntimeError):
                preflight.verify()


if __name__ == "__main__":
    unittest.main()
