#!/usr/bin/env python3
"""「イケメンコンサル」用に、男性向けセルフアップ(清潔感/モテ/自己投資)アカウントの新規ドラフトを自動生成する。

設計の要点:
- テーマ = 育成系(エンゲージ重視・アフィ無し) と 紹介系(アフィリンク付き) の2層。
- 紹介系は products.json の「もしも かんたんリンク」付き商品から1つ選ぶ。
  → リンクが1つも無い間は自動的に「育成系のみ」を生成する(=ウォームアップが内蔵される)。
- アフィ投稿には景品表示法(ステマ規制)対応の PR 開示文を必ず付与。文面はランダムで分散
  (同一文連投による X のスパム判定を避ける)。

Usage:
    python3 scripts/generate_draft.py
    python3 scripts/generate_draft.py --theme grooming   # カテゴリ強制
    python3 scripts/generate_draft.py --force             # pending に残っていても追加生成
    python3 scripts/generate_draft.py --no-aff            # 今回はアフィ無し(育成投稿)を強制
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from llm_gemini import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PENDING = ROOT / "drafts" / "pending"
POSTED = ROOT / "drafts" / "posted"
LOGS = ROOT / "logs"
PRODUCTS = ROOT / "products.json"

MODEL = "claude-opus-4-8"

# --- PR開示文(ステマ規制 必須)。アフィ投稿に1つランダム付与して連投の同一性を避ける ---
PR_DISCLOSURES = [
    "※アフィリエイト広告を含みます #PR",
    "#PR（アフィリエイト広告を利用しています）",
    "※広告（アフィリエイト）を含みます #PR",
    "#PR ※リンクから購入で運営に収益が入ります",
    "※本投稿はプロモーションを含みます #PR",
]

# --- テーマ: 育成系(アフィ無し) と 紹介系(アフィ有り) ---
# is_affiliate=True のテーマは products.json のカテゴリと紐づく。
THEMES = {
    # ===== 育成系(フォロワーを増やす・拡散される。アフィ無し) =====
    "seikan_aruaru": {
        "label": "清潔感・モテのあるある／気づき・共感",
        "ratio": 20,
        "is_affiliate": False,
        "seeds": [
            "「清潔感がある人」は顔じゃなく、眉・爪・襟元の3点で決まっていた話",
            "髪型はキマってるのに清潔感が出ない人の共通点(肌と眉)",
            "香りは『つけすぎない人』がいちばん好印象という気づき",
            "値段より『サイズが合ってない服』がいちばんダサく見える",
            "笑ったときの歯と、話すときの距離感で第一印象は決まる",
            "清潔感は生まれつきじゃなく、整える習慣で後から作れる",
        ],
    },
    "jikotoshi_chie": {
        "label": "自己投資・習慣の小ネタ(育成)",
        "ratio": 16,
        "is_affiliate": False,
        "seeds": [
            "朝の5分を『洗顔＋日焼け止め』に回すだけで一日の印象が変わる",
            "自己投資は『高い物』より『毎日触れる物』から変えると効く",
            "鏡を見る回数を増やすだけで姿勢と表情が自然に整う",
            "1日1個だけ『昨日の自分より整える』を積む習慣の話",
            "睡眠を削った日の肌と機嫌は、相手に意外とバレている",
            "完璧を目指さず『清潔感の合格点』を毎日キープする考え方",
        ],
    },
    # ===== 紹介系(アフィリンク付き。products.json の category と一致) =====
    "grooming": {
        "label": "男性美容・グルーミング(スキンケア/シェーブ/眉/ヘア/香り)",
        "ratio": 18,
        "is_affiliate": True,
        "seeds": [
            "洗顔と保湿を変えただけで『肌きれいだね』と言われた実感",
            "眉を整えただけで顔の清潔感が一段上がった",
            "深剃りシェーバーで青ひげの印象が消えた",
            "ヘアバームで束感と清潔感が出て、香りも控えめにまとまる",
            "つけすぎない香り(練り香水/控えめな香水)の効かせ方",
            "口臭・舌・歯間ケアを始めてから会話の距離が変わった",
        ],
    },
    "fashion": {
        "label": "メンズファッション(サイズ感/靴/小物/シンプル配色)",
        "ratio": 16,
        "is_affiliate": True,
        "seeds": [
            "ジャストサイズの白Tに替えただけで全体が垢抜けた",
            "靴を綺麗に保つだけで足元から信頼感が出る",
            "色は3色まで、シンプルが結局いちばん好印象",
            "体型に合うシルエットを知ると、安物でも様になる",
            "小物(時計やバッグ)を1個だけ良い物にする効果",
        ],
    },
    "renai": {
        "label": "恋愛・モテ・デート(自信/会話/プロフィールの整え方)",
        "ratio": 16,
        "is_affiliate": True,
        "seeds": [
            "マッチングは写真の盛りより『清潔感が伝わる1枚』で変わった",
            "会話は質問より『リアクション』を変えたら続くようになった",
            "デートは店選びより『余裕のある態度』が効く",
            "自信は中身じゃなく『整えた事実』が後から作ってくれる",
            "連絡は即レスより『心地よいリズム』が大事だった気づき",
        ],
    },
    "business": {
        "label": "ビジネス・自己投資(筋トレ/読書/学習/環境)",
        "ratio": 14,
        "is_affiliate": True,
        "seeds": [
            "筋トレを始めたら姿勢と自信が変わって仕事にも効いた",
            "読書習慣をつけたら会話の引き出しが増えた",
            "時間術の道具や手帳で、朝のバタバタが消えた",
            "学習(英語やスキル)への自己投資がいちばんコスパ良かった",
            "整った部屋が、整った自分を作る(環境への投資)",
        ],
    },
}

AFFILIATE_THEMES = [k for k, v in THEMES.items() if v["is_affiliate"]]


def load_products() -> list[dict]:
    """products.json から『もしも かんたんリンク付き』の商品だけ返す。"""
    if not PRODUCTS.exists():
        return []
    try:
        data = json.loads(PRODUCTS.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("products", []) if isinstance(data, dict) else data
    valid = []
    for product in items:
        if not isinstance(product, dict):
            continue
        link = product.get("link", "").strip()
        if not link:
            continue
        parsed = urlparse(link)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"商品リンクは有効なHTTPS URL必須: {product.get('name', '(名称なし)')}")
        valid.append(product)
    return valid


def affiliate_allowed_today(max_per_day: int | None = None) -> bool:
    """Pendingを含め、1日のアフィリエイト生成数を上限以内に保つ。"""
    limit = max_per_day if max_per_day is not None else int(os.getenv("X_AFFILIATE_MAX_PER_DAY", "1"))
    prefix = dt.datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    count = 0
    for directory in (PENDING, POSTED):
        if directory.exists():
            count += sum(1 for p in directory.iterdir() if p.is_file() and p.suffix in {".md", ".txt"} and p.name.startswith(prefix) and "_aff" in p.name)
    return count < limit


def pick_product(category: str, products: list[dict]) -> dict | None:
    pool = [p for p in products if p.get("category") == category]
    if not pool:
        pool = products  # カテゴリ一致が無ければ全体から
    return random.choice(pool) if pool else None


def pick_theme(forced: str | None, allow_affiliate: bool) -> tuple[str, dict]:
    if forced:
        if forced not in THEMES:
            raise ValueError(f"theme は {list(THEMES)} のいずれか")
        return forced, THEMES[forced]
    keys = [k for k, v in THEMES.items() if allow_affiliate or not v["is_affiliate"]]
    weights = [THEMES[k]["ratio"] for k in keys]
    k = random.choices(keys, weights=weights, k=1)[0]
    return k, THEMES[k]


def recent_to_avoid(n: int = 12) -> list[str]:
    if not POSTED.exists():
        return []
    files = sorted(
        (p for p in POSTED.iterdir() if p.suffix not in {".json"} and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:n]
    out = []
    for f in files:
        try:
            txt = f.read_text(encoding="utf-8").strip()
            if txt:
                out.append(txt[:120])
        except Exception:
            pass
    return out


PERSONA = """あなたは X(旧Twitter)の男性向けセルフアップ系アカウント「イケメンコンサル」の中の人。
20〜30代の男性に向けて、清潔感・モテ・自己投資(美容/ファッション/恋愛/ビジネス)を、
等身大かつ少しだけ先導する『ちょっと先を行く先輩』の目線で発信している。

# 声・トーン
- 上から教えない。でも芯はある。「自分も通ってきた」先輩が後輩にそっと教える温度
- 一人称は「自分」中心(複数形は「自分たち」)。常体ベースで、ですますが自然に混ざってOK
- 絵文字は0〜2個まで(✨💪🧴👔☕ 等、内容に合うものを軽く)。盛らない。チャラくしない
- 体験・気づきベースで具体に。『何を』『どう変えたら』『どう変わったか』を1つだけ刺さるように
- 煽り・誇大(『人生変わる』『絶対モテる』連発)はしない。地に足のついた『清潔感は作れる』を大事に
- 短文で読みやすく。改行を効かせて詰め込みすぎない

# 絶対NG
- 効果の断定・医療/健康/美容の誇大表現(「絶対生える」「必ず痩せる」「絶対モテる」等)
- 女性蔑視・ナンパ自慢・性的に露骨な表現、ルッキズムで他者を見下す表現
- 「陰キャ」「弱者男性」など読者や他者を見下す言葉、射幸心を煽る断定
- 政治・宗教、他者批判、炎上狙い
- 嘘の体験(持っていないのに使った断定)→ 『気になってる』『良さそう』の温度に留める"""


def build_user_msg(theme_label: str, seed: str, product: dict | None, avoid: list[str]) -> str:
    avoid_block = ""
    if avoid:
        avoid_block = "\n# 直近の投稿(似た書き出し・角度を避ける)\n" + "\n".join(f"- {t}" for t in avoid)

    if product:
        prod_block = (
            f"\n# 紹介する商品\n商品: {product.get('name','')}\n"
            f"ひとこと: {product.get('note','')}\n"
            "この商品を主役に、上の『ネタの種』の体験と絡めて自然に紹介して。"
            "スペック羅列でなく『どう印象/自分が変わったか』を1点。"
            "商品リンクとPR表記はこちらで後付けするので本文に URL は書かないで。"
        )
    else:
        prod_block = (
            "\n# 今回はアフィ無しの育成投稿。商品宣伝はせず、気づき・あるある・小ネタで"
            "『フォローしたくなる』内容に。"
        )

    return (
        f"# 今回のテーマ\n{theme_label}\nネタの種: {seed}"
        + prod_block
        + avoid_block
        + "\n\n上記をもとに、X に投稿する本文を1つだけ。説明や引用符は不要、本文だけ返す。"
    )


def generate(theme_label: str, seed: str, product: dict | None, avoid: list[str]) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(".env に ANTHROPIC_API_KEY が未設定")
    client = Anthropic(api_key=api_key)
    res = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=PERSONA,
        messages=[{"role": "user", "content": build_user_msg(theme_label, seed, product, avoid)}],
    )
    return "".join(b.text for b in res.content if b.type == "text").strip()


def assemble(body: str, product: dict | None) -> str:
    """ドラフト本文を組み立てる。

    アフィの場合は先頭に `aff: <link>` ヘッダを付ける(本文URLは付けない)。
    推敲(polish)は本文だけを書き直し、リンク + PR開示文は pipeline が推敲後に後付けする。
    こうすることで推敲工程がURLやPR表記を壊さない。
    """
    if not product:
        return body
    link = product.get("link", "").strip()
    return f"aff: {link}\n{body}"


def append_log(payload: dict) -> None:
    LOGS.mkdir(exist_ok=True)
    payload = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), **payload}
    with (LOGS / "generate.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    if force:
        args.remove("--force")
    no_aff = "--no-aff" in args
    if no_aff:
        args.remove("--no-aff")
    theme_forced = None
    if "--theme" in args:
        theme_forced = args[args.index("--theme") + 1]

    PENDING.mkdir(parents=True, exist_ok=True)
    existing = [p for p in PENDING.iterdir() if p.is_file() and not p.name.startswith(".")]
    if existing and not force:
        print(f"[skip] pending に {len(existing)} 件残っています(--force で追加生成)")
        append_log({"event": "skipped", "pending_count": len(existing)})
        return 0

    products = load_products()
    allow_aff = bool(products) and not no_aff and affiliate_allowed_today()
    if not products:
        print("[info] products.json に有効な もしもリンク が無いため、育成投稿(アフィ無し)のみ生成します")
    elif not affiliate_allowed_today():
        print("[info] 本日のアフィリエイト上限に達したため、育成投稿のみ生成します")

    theme_key, theme = pick_theme(theme_forced, allow_aff)
    product = None
    if theme["is_affiliate"] and allow_aff:
        product = pick_product(theme_key, products)
    seed = random.choice(theme["seeds"])

    print(f"[theme] {theme_key} / {theme['label']}")
    if product:
        print(f"[product] {product.get('name')}  ->  {product.get('link')}")
    print(f"[seed] {seed}\n")

    body = generate(theme["label"], seed, product, recent_to_avoid())
    final = assemble(body, product)
    print(f"[draft]\n{final}\n")

    tag = "aff" if product else "grow"
    fname = f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}_{theme_key}_{tag}.md"
    (PENDING / fname).write_text(final, encoding="utf-8")
    append_log({
        "event": "generated", "file": fname, "theme": theme_key,
        "affiliate": bool(product), "product": (product or {}).get("name"),
        "chars": len(final),
    })
    print(f"[saved] drafts/pending/{fname}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
