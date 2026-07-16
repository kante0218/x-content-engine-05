#!/usr/bin/env python3
"""今回のcron起動で投稿すべきか判定する(1日ちょうどX_DAILY_TARGET回・ランダム時刻)。

仕組み(リザーバ方式):
- 1日に複数の候補スロット(cronで起動)を用意し、そのうち TARGET 個だけを確率的に選ぶ。
- 各スロットで `random() < 残り必要数 / 残りスロット数` なら投稿。
- これで「どのスロットに当たるか」は毎日ランダムに散りつつ、合計はちょうど TARGET 回に収束する。
- GitHubのcronが多少遅延/欠落しても、残りスロットで自動的に確率を上げて吸収する。

判定材料:
- 今日すでに投稿した数 = drafts/posted/ にある今日(JST)の日付プレフィックスの .md 数
- 残りスロット数 = SLOTS_JST のうち「今(JST)以降」のもの(遅延吸収で少し過去も含む)

exit 0 = 投稿する / exit 1 = 今回はスキップ
"""
from __future__ import annotations

import datetime as dt
import os
import random
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
POSTED = ROOT / "drafts" / "posted"
JST = ZoneInfo("Asia/Tokyo")

# cron(.github/workflows/post.yml)と同期する候補スロット(JST, 時, 分)。不規則な分にしてbot感を消す。
SLOTS_JST = [
    (7, 50), (9, 5), (10, 20), (11, 40), (12, 55), (14, 15),
    (15, 30), (16, 50), (18, 10), (19, 25), (20, 40), (21, 55),
]

# cronは数分〜十数分遅延するので、「今以降のスロット」を数える際に過去側へこの分だけ許容する
DELAY_TOLERANCE_MIN = 25


def posted_today(today: dt.date) -> int:
    if not POSTED.exists():
        return 0
    prefix = today.strftime("%Y%m%d")
    return sum(
        1 for p in POSTED.iterdir()
        if p.suffix == ".md" and p.name.startswith(prefix)
    )


def slots_remaining(now: dt.datetime) -> int:
    cutoff = now - dt.timedelta(minutes=DELAY_TOLERANCE_MIN)
    cutoff_min = cutoff.hour * 60 + cutoff.minute
    return sum(1 for h, m in SLOTS_JST if h * 60 + m >= cutoff_min)


def daily_target(today: dt.date, base: int) -> int:
    """1日の投稿数を base-1 〜 base+1 でゆらす(bot感を消す)。

    日付から決定的に決めるので、その日の全スロットで必ず同じ値になり、
    リザーバ判定が破綻しない(乱数だとスロット間で目標がブレてしまう)。
    """
    x = (today.toordinal() * 2654435761) & 0xFFFFFFFF  # Knuth乗算でビットを撹拌
    x ^= x >> 16
    x = (x * 2246822519) & 0xFFFFFFFF
    x ^= x >> 13
    spread = x % 3  # 0,1,2 を日替わりで決定的に
    return max(1, base - 1 + spread)


def main() -> int:
    base = int(os.getenv("X_DAILY_TARGET", "4"))
    now = dt.datetime.now(JST)
    target = daily_target(now.date(), base)
    done = posted_today(now.date())
    needed = target - done
    remaining = max(slots_remaining(now), 1)

    if needed <= 0:
        print(f"[skip] 本日は既に {done}/{target} 投稿済み")
        return 1

    if needed >= remaining:
        # 残りスロットが必要数以下 → 確実に投稿しないと足りない
        print(f"[post] needed={needed} >= remaining={remaining} → 確定投稿 (done={done})")
        return 0

    prob = needed / remaining
    roll = random.random()
    if roll < prob:
        print(f"[post] roll={roll:.3f} < p={prob:.3f} (needed={needed}/remaining={remaining}, done={done})")
        return 0
    print(f"[skip] roll={roll:.3f} >= p={prob:.3f} (needed={needed}/remaining={remaining}, done={done})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
