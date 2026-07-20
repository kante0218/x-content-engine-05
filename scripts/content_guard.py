"""Deterministic duplicate detection for generated X posts."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


def valid_https_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"https?://\S+", "", text)
    return re.sub(r"\s+", "", text)


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def trigrams(text: str) -> set[str]:
    value = normalize(text)
    if len(value) < 3:
        return {value} if value else set()
    return {value[i:i + 3] for i in range(len(value) - 2)}


def similarity(left: str, right: str) -> float:
    a, b = trigrams(left), trigrams(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def posted_texts(posted: Path, limit: int = 360) -> list[str]:
    if not posted.exists():
        return []
    out: list[str] = []
    files = sorted(posted.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        if len(out) >= limit:
            break
        try:
            if path.name.endswith(".result.json"):
                text = json.loads(path.read_text(encoding="utf-8")).get("text", "")
            elif path.suffix in {".md", ".txt"}:
                text = path.read_text(encoding="utf-8")
                text = re.sub(r"^aff\s*:\s*\S+\s*", "", text, flags=re.I)
            else:
                continue
            if text.strip():
                out.append(text)
        except (OSError, ValueError, TypeError):
            continue
    return out


def find_duplicate(text: str, posted: Path, threshold: float = 0.72) -> tuple[bool, float]:
    digest = content_hash(text)
    best = 0.0
    for previous in posted_texts(posted):
        if content_hash(previous) == digest:
            return True, 1.0
        best = max(best, similarity(text, previous))
    return best >= threshold, best
