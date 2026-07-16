#!/usr/bin/env python3
"""drafts/pending の最古ファイルを推敲 → 投稿 → posted/ に移動。

- X_LIVE_POST=true のときだけ実投稿。false ならドライラン(推敲結果を logs に書くだけ)。
- 失敗したら drafts/failed/ に移動して理由ログを残す。
- ドラフトの1行目が `quote: <URL>` の場合は、そのツイートを引用RT扱いで投稿する。

Usage:
    python3 scripts/pipeline.py            # 通常
    python3 scripts/pipeline.py --dry-run  # 実投稿せず推敲のみ
    python3 scripts/pipeline.py --length 長文
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "scripts"))

from polish_draft import polish  # noqa: E402
from post_tweet import post  # noqa: E402

HANDLE = os.getenv("X_HANDLE", "ikemen_consult")
PENDING = ROOT / "drafts" / "pending"
POSTED = ROOT / "drafts" / "posted"
FAILED = ROOT / "drafts" / "failed"
LOGS = ROOT / "logs"

QUOTE_LINE_RE = re.compile(r"^\s*quote\s*:\s*(\S+)\s*$", re.IGNORECASE)
AFF_LINE_RE = re.compile(r"^\s*aff\s*:\s*(\S+)\s*$", re.IGNORECASE)
TWEET_ID_RE = re.compile(r"status/(\d+)")

# PR開示文(ステマ規制 必須)。アフィ投稿に1つランダム付与し連投の同一性を避ける。
PR_DISCLOSURES = [
    "※アフィリエイト広告を含みます #PR",
    "#PR（アフィリエイト広告を利用しています）",
    "※広告（アフィリエイト）を含みます #PR",
    "#PR ※リンクから購入で運営に収益が入ります",
    "※本投稿はプロモーションを含みます #PR",
]


def oldest_pending() -> Path | None:
    files = sorted(p for p in PENDING.iterdir() if p.is_file() and not p.name.startswith("."))
    return files[0] if files else None


def append_log(name: str, payload: dict) -> None:
    LOGS.mkdir(exist_ok=True)
    log_path = LOGS / "pipeline.log"
    payload = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "file": name, **payload}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_quote_header(raw: str) -> tuple[str | None, str]:
    """ドラフト先頭の `quote: <URL>` 行を抽出。なければ (None, raw) を返す。"""
    lines = raw.splitlines()
    if not lines:
        return None, raw
    m = QUOTE_LINE_RE.match(lines[0])
    if not m:
        return None, raw
    url = m.group(1)
    id_m = TWEET_ID_RE.search(url)
    if not id_m:
        raise ValueError(f"quote URLからtweet_idを抽出できません: {url}")
    body = "\n".join(lines[1:]).lstrip()
    return id_m.group(1), body


def parse_aff_header(raw: str) -> tuple[str | None, str]:
    """ドラフト先頭の `aff: <URL>` 行(アフィリンク)を抽出。なければ (None, raw)。"""
    lines = raw.splitlines()
    if not lines:
        return None, raw
    m = AFF_LINE_RE.match(lines[0])
    if not m:
        return None, raw
    return m.group(1), "\n".join(lines[1:]).lstrip()


def with_affiliate_footer(text: str, aff_link: str | None) -> str:
    """推敲後の本文に、アフィリンク + ランダムPR開示文を後付けする。"""
    if not aff_link:
        return text
    return f"{text}\n\n👉 {aff_link}\n{random.choice(PR_DISCLOSURES)}"


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    live = os.getenv("X_LIVE_POST", "false").lower() == "true" and not dry_run

    length = None
    if "--length" in sys.argv:
        i = sys.argv.index("--length")
        length = sys.argv[i + 1]

    draft_path = oldest_pending()
    if draft_path is None:
        append_log("(none)", {"event": "no_pending"})
        print("pending にドラフトはありません。drafts/pending/ に .md か .txt を置いてください。", file=sys.stderr)
        return 0

    raw = draft_path.read_text(encoding="utf-8")
    print(f"[draft] {draft_path.name}\n---\n{raw}\n---")

    # 先に aff: ヘッダ(アフィリンク)を剥がしてから quote: を見る。
    aff_link, raw = parse_aff_header(raw)
    if aff_link:
        print(f"[affiliate] link={aff_link}")

    try:
        quote_id, body = parse_quote_header(raw)
    except Exception as e:
        FAILED.mkdir(exist_ok=True)
        shutil.move(str(draft_path), str(FAILED / draft_path.name))
        append_log(draft_path.name, {"event": "parse_failed", "error": str(e)})
        print(f"[parse ERROR] {e}", file=sys.stderr)
        return 1

    if quote_id:
        print(f"[quote_rt] quote_tweet_id={quote_id}")

    try:
        polished = polish(body, length=length)
    except Exception as e:
        FAILED.mkdir(exist_ok=True)
        shutil.move(str(draft_path), str(FAILED / draft_path.name))
        append_log(draft_path.name, {"event": "polish_failed", "error": str(e)})
        print(f"[polish ERROR] {e}", file=sys.stderr)
        return 1
    polished = with_affiliate_footer(polished, aff_link)
    print(f"[polished] ({len(polished)}文字)\n---\n{polished}\n---")

    if not live:
        append_log(
            draft_path.name,
            {"event": "dry_run", "polished": polished, "chars": len(polished), "quote_tweet_id": quote_id},
        )
        print("[dry-run] 実投稿はしませんでした。X_LIVE_POST=true で本番投稿。")
        return 0

    try:
        result = post(polished, quote_tweet_id=quote_id)
    except Exception as e:
        FAILED.mkdir(exist_ok=True)
        shutil.move(str(draft_path), str(FAILED / draft_path.name))
        append_log(draft_path.name, {"event": "post_failed", "error": str(e), "polished": polished})
        print(f"[post ERROR] {e}", file=sys.stderr)
        return 1

    tweet_id = result.get("data", {}).get("id")
    POSTED.mkdir(exist_ok=True)
    posted_name = f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{draft_path.name}"
    shutil.move(str(draft_path), str(POSTED / posted_name))
    (POSTED / (posted_name + ".result.json")).write_text(
        json.dumps(
            {"tweet_id": tweet_id, "text": polished, "quote_tweet_id": quote_id, "raw": result},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    event_payload = {
        "event": "posted",
        "tweet_id": tweet_id,
        "url": f"https://x.com/{HANDLE}/status/{tweet_id}",
    }
    if quote_id:
        event_payload["quote_tweet_id"] = quote_id
    append_log(posted_name, event_payload)
    print(f"[posted] https://x.com/{HANDLE}/status/{tweet_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
