#!/usr/bin/env python3
"""「イケメンコンサル」(X) 向けに、ドラフトを推敲する。

Usage:
    python3 scripts/polish_draft.py drafts/pending/xxx.md
    echo "原文..." | python3 scripts/polish_draft.py -
    python3 scripts/polish_draft.py xxx.md --length 長文

文字数上限は .env の X_MAX_CHARS(既定280)。
X Premium長文ポストを使う場合は X_MAX_CHARS=900 などにすると、推敲も長文化する。
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "claude-opus-4-8"


def _max_chars() -> int:
    try:
        return int(os.getenv("X_MAX_CHARS", "280"))
    except ValueError:
        return 280


SYSTEM_PROMPT = """あなたは X(旧Twitter)の男性向けセルフアップ系アカウント「イケメンコンサル」の中の人として、投稿する単体ツイートを書く。
原文ドラフトを、自分の言葉で書き直してください。

# 大前提
- AIが書いたとバレないこと。流暢すぎる説明・三段論法・啓蒙臭・テンプレ構成を消す
- 毎回違う角度から入って、違う場所で終わる。締めの定型(「ぜひ試してみて」連発等)は避ける
- 後輩に「これやると変わるよ」とそっと教えるくらいの距離感。等身大だが芯はある

# 中の人の人物像(忠実に守る)
- 自分自身も垢抜けてきた20〜30代の男性。清潔感・美容・ファッション・恋愛・自己投資を自分で試して『地味に効いたもの』を共有している
- 専門家ぶらない。完璧でもない。失敗談やゆるい本音もたまに出してよい

# 口調・トーン(絶対ルール)
- 一人称は「自分」中心(複数形は「自分たち」)。常体ベースで、ですますが自然に混ざってOK
- 体験・気づきベースで具体に。『何を』『どう変えたら』『どう変わったか』を1つだけ刺さるように。スペック羅列はしない
- 煽り・誇大表現は禁止(「神」「人生変わる」「絶対モテる」「絶対痩せる」の連発、過度な断定)
- 改行を効かせて読みやすく。短文〜中文中心。詰め込みすぎない
- 商品紹介でも『売り込み感』を出さない。あくまで『試したら良かった共有』の温度。チャラくしない

# 絶対NG表現
- 効果の断定・医療/健康/美容の誇大表現(「絶対生える」「必ず痩せる」「絶対モテる」等)
- 嘘の体験(持っていないのに使った断定)→『気になってる』『良さそう』に留める
- 女性蔑視・ナンパ自慢・性的に露骨な表現、ルッキズムで他者を見下す表現
- 「陰キャ」「弱者男性」「情弱」など読者や他者を見下す言葉、射幸心を煽る断定
- 他者批判、政治・宗教、炎上狙い

# 投稿軸(原文がどれに該当するかを判断して書く)
- 清潔感・モテのあるある／気づき(育成。共感でフォローしたくなる)
- 自己投資・習慣の小ネタ(育成)
- 男性美容/グルーミング・メンズファッション・恋愛/モテ・ビジネス自己投資の紹介(体験ベースで自然に)

# 役割
- フォロワーに見せたい姿は「清潔感があって、自分を整え続けている、ちょっと先を行く先輩」
- ターゲット読者は、垢抜けたい・モテたい・自分を変えたい20〜30代男性
- 押し付けず、共感と『自分も整えたくなる』を両立させる

# 絵文字
- 0〜2個まで。このあとユーザーメッセージで指定する方針に従う

# 出力フォーマット
推敲後の本文だけ返す。説明・前置き・引用符・「以下が...」は一切出力しない。
※リンクURLやPR表記は別工程で付与するので、本文には絶対に入れない。"""


# 男性向けセルフアップ系の、清潔感のある絵文字パレット(盛らない/チャラくしない)。
EMOJI_POOL = ["✨", "💪", "🧴", "👔", "👞", "🕶️", "📚", "☕", "🔥", "💈", "💡"]


def _emoji_instruction() -> str:
    r = random.random()
    if r < 0.4:
        return "# 今回の絵文字\n- 今回は**絵文字を使わない**か、最小限に\n"
    n = random.choice([1, 1, 2])
    picks = ", ".join(f"`{e}`" for e in random.sample(EMOJI_POOL, n))
    return (
        "# 今回の絵文字\n"
        f"- 今回は**絵文字を{n}個まで**使ってよい(候補: {picks} などから内容に合うもの)\n"
        "- 文末固定にせず自然な位置に。盛りすぎない・チャラくしない\n"
    )


def _length_instruction(forced: str | None = None) -> tuple[str, str]:
    limit = _max_chars()
    # 長さは毎回ばらす(bot感を消すため、短文〜長文をごちゃ混ぜにする)。
    if limit <= 300:
        # 通常(無料/280)アカウント
        modes = [
            (5, "短文", "今回は**短文**で。1〜3行、40〜110文字。気づき/あるあるを1つだけ、切れ味よく。説明しすぎない。"),
            (4, "中文", "今回は中文で。3〜5行、150〜220文字程度。体験を1つと、どう変わったかの実感を添える。改行を効かせる。"),
            (2, "長文", f"今回は**やや長文**で。{min(limit-5, 230)}文字前後、**絶対に{limit}文字を超えない**。状況+体験+実感の流れで、改行を効かせて読みやすく。"),
        ]
    else:
        # 長め(Threads 等、上限が大きい場合): 短文〜中長文を混ぜる
        target = min(limit - 60, 380)
        modes = [
            (5, "短文", "今回は**短文**で。1〜3行、50〜130文字。気づき/あるあるを1つだけ、切れ味よく。前置き・まとめは要らない。"),
            (4, "中文", "今回は中文で。3〜5行、150〜250文字程度。体験を1つと、どう変わったかの実感を添える。改行を効かせる。"),
            (2, "中長文", f"今回は中長文で。{target}文字前後、**絶対に{limit}文字を超えない**。状況+体験+実感を、改行を効かせて読みやすく。"),
        ]
    if forced:
        for _, label, instr in modes:
            if label == forced:
                return label, instr
        raise ValueError(f"length は {[m[1] for m in modes]} のいずれか")
    weights = [w for w, _, _ in modes]
    choice = random.choices(modes, weights=weights, k=1)[0]
    return choice[1], choice[2]


def polish(draft: str, length: str | None = None) -> str:
    draft = draft.strip()
    if not draft:
        raise ValueError("空のドラフトは推敲できません")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(".env に ANTHROPIC_API_KEY が未設定")

    limit = _max_chars()
    client = Anthropic(api_key=api_key)

    # 上限超過は自動でリトライ: 2回目以降は短い長さモードを強制し、明示的に上限を伝える。
    fallback_lengths = [None, "中長文", "中文"] if limit > 300 else [None, "中文", "短文"]
    if length is not None:
        fallback_lengths = [length, "中文", "短文"]

    last_text = ""
    for attempt, len_mode in enumerate(fallback_lengths, start=1):
        try:
            label, length_instruction = _length_instruction(len_mode)
        except ValueError:
            label, length_instruction = _length_instruction(None)
        emoji_instruction = _emoji_instruction()
        over_note = ""
        if attempt > 1:
            over_note = (
                f"\n# 重要(前回オーバー)\n- 前回は{len(last_text)}文字で上限{limit}を超えました。"
                f"今回は**必ず{limit}文字以内**に収めてください。内容を削ってでも短くする。\n"
            )
        user_msg = (
            "以下のドラフトをXに投稿する自分のツイートに書き直してください。\n\n"
            f"{length_instruction}\n\n"
            f"{emoji_instruction}"
            f"{over_note}\n"
            "---\n"
            f"{draft}\n"
            "---"
        )
        res = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(block.text for block in res.content if block.type == "text").strip()
        last_text = text
        if len(text) <= limit:
            sys.stderr.write(f"[length_mode={label} chars={len(text)} limit={limit} attempt={attempt}]\n")
            return text
        sys.stderr.write(f"[over limit] {len(text)}>{limit} (attempt={attempt}/{len(fallback_lengths)}) → 短く再推敲\n")

    raise RuntimeError(f"推敲結果が{len(last_text)}文字>{limit}。{len(fallback_lengths)}回試しても収まりませんでした")


def main() -> int:
    args = sys.argv[1:]
    length = None
    if "--length" in args:
        i = args.index("--length")
        length = args.pop(i + 1)
        args.pop(i)
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    arg = args[0]
    if arg == "-":
        draft = sys.stdin.read()
    else:
        draft = Path(arg).read_text(encoding="utf-8")
    print(polish(draft, length=length))
    return 0


if __name__ == "__main__":
    sys.exit(main())
