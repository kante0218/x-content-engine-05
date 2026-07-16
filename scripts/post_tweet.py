#!/usr/bin/env python3
"""X API v2 POST /2/tweets を OAuth 1.0a User Context で叩く最小スクリプト。

Usage:
    python3 scripts/post_tweet.py "投稿本文"
    echo "投稿本文" | python3 scripts/post_tweet.py -

文字数上限は .env の X_MAX_CHARS で調整(既定280)。
X Premium(長文ポスト)を使う場合は X_MAX_CHARS=4000 などにする。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

TWEETS_ENDPOINT = "https://api.x.com/2/tweets"


def _max_chars() -> int:
    try:
        return int(os.getenv("X_MAX_CHARS", "280"))
    except ValueError:
        return 280


def post(text: str, quote_tweet_id: str | None = None) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("空の投稿は送れません")
    limit = _max_chars()
    if len(text) > limit:
        raise ValueError(f"{len(text)}文字 > {limit}文字。先に推敲してください")

    required = {
        "X_CONSUMER_KEY": os.getenv("X_CONSUMER_KEY"),
        "X_CONSUMER_SECRET": os.getenv("X_CONSUMER_SECRET"),
        "X_ACCESS_TOKEN": os.getenv("X_ACCESS_TOKEN"),
        "X_ACCESS_TOKEN_SECRET": os.getenv("X_ACCESS_TOKEN_SECRET"),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f".env に未設定: {', '.join(missing)}")

    session = OAuth1Session(
        client_key=required["X_CONSUMER_KEY"],
        client_secret=required["X_CONSUMER_SECRET"],
        resource_owner_key=required["X_ACCESS_TOKEN"],
        resource_owner_secret=required["X_ACCESS_TOKEN_SECRET"],
    )
    payload: dict = {"text": text}
    if quote_tweet_id:
        payload["quote_tweet_id"] = quote_tweet_id
    res = session.post(TWEETS_ENDPOINT, json=payload, timeout=30)
    if res.status_code != 201:
        raise RuntimeError(f"X API エラー status={res.status_code} body={res.text}")
    return res.json()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    arg = sys.argv[1]
    text = sys.stdin.read() if arg == "-" else arg
    result = post(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
