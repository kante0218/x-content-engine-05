#!/usr/bin/env python3
"""Validate OAuth credentials and confirm they belong to X_HANDLE."""
from __future__ import annotations

import json
import os
import sys

from requests_oauthlib import OAuth1Session

ME_ENDPOINT = "https://api.x.com/2/users/me"


def credentials() -> dict[str, str]:
    keys = ("X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    values = {key: os.getenv(key, "").strip() for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"未設定のX認証情報: {', '.join(missing)}")
    return values


def verify() -> dict:
    values = credentials()
    session = OAuth1Session(
        client_key=values["X_CONSUMER_KEY"], client_secret=values["X_CONSUMER_SECRET"],
        resource_owner_key=values["X_ACCESS_TOKEN"],
        resource_owner_secret=values["X_ACCESS_TOKEN_SECRET"],
    )
    response = session.get(ME_ENDPOINT, params={"user.fields": "username"}, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"X preflightエラー status={response.status_code} body={response.text}")
    data = response.json()
    expected = os.getenv("X_HANDLE", "").lstrip("@").lower()
    actual = data.get("data", {}).get("username", "").lower()
    if expected and actual != expected:
        raise RuntimeError(f"Xアカウント不一致: expected=@{expected} actual=@{actual}")
    return data


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"[preflight ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
