# x-automation-ikemen

@ikemen_consult（イケメンコンサル）向け **X アフィリエイト投稿自動化**。
20〜30代男性の清潔感・モテ・自己投資（美容/ファッション/恋愛/ビジネス）の投稿を、生成→推敲→投稿まで自動化する。

- **育成系**（清潔感あるある・自己投資の小ネタ）＝アフィ無しでフォロワーを増やす
- **紹介系**（グルーミング／ファッション／恋愛／ビジネス）＝`products.json` の「もしも かんたんリンク」を貼る
- アフィ投稿には**景品表示法（ステマ規制）対応の PR 開示文を自動付与**（文面はランダム分散）

## 仕組み

```
generate_draft.py  →  drafts/pending/  →  pipeline.py(polish→post)  →  drafts/posted/
```

- `products.json` に**有効なリンクが1件も無い間は、育成投稿（アフィ無し）だけが生成される**
  = アカウント開設直後のウォームアップが自動で回る。
- リンクを足した瞬間に、紹介系テーマでアフィ投稿も混ざり始める。
- アフィリンクはドラフト先頭の `aff: <URL>` ヘッダで持ち、**推敲後**に「👉リンク＋PR表記」を後付け。

## セットアップ（あなたの作業）

1. **X Developer App を @ikemen_consult 用に新規作成**（他アカウントとは別アプリが必要）
   - https://developer.x.com → Projects & Apps
   - App permissions を **Read and Write** に設定（投稿に必須）
   - Keys and tokens で Consumer Key/Secret と Access Token/Secret を発行
2. GitHub リポの **Settings → Secrets and variables → Actions** に登録：
   - `X_CONSUMER_KEY` / `X_CONSUMER_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET`
   - （`ANTHROPIC_API_KEY` は登録済み）
   - （任意）Variables に `X_HANDLE`（実ハンドル）/ `X_MAX_CHARS=230`
   - **`X_ACCESS_TOKEN` を登録した瞬間に自動で本番投稿が始まる**（未登録の間は安全にdry-run）。
3. `products.json` に**もしもアフィリエイトの「かんたんリンク」**を貼る（`link` 欄）。
   - `category` は `grooming` / `fashion` / `renai` / `business` のいずれか。
4. GitHub Actions の `auto-post` ワークフローが**1日3〜5回ランダム時刻**で自動投稿。
   - 最初は `products.json` を空のままにして**育成投稿だけで2週間ほど回す**のを推奨。

## ローカルでの確認

```bash
cd ~/x-automation-ikemen
cp .env.example .env        # ANTHROPIC_API_KEY と X_* を埋める
./venv/bin/python scripts/generate_draft.py            # ドラフト生成
./venv/bin/python scripts/pipeline.py --dry-run        # 推敲のみ(投稿しない)
# 本番投稿は .env で X_LIVE_POST=true
```

### 便利なフラグ
- `generate_draft.py --theme grooming|fashion|renai|business|seikan_aruaru|jikotoshi_chie` … テーマ強制
- `generate_draft.py --no-aff` … 今回はアフィ無し（育成投稿）を強制
- `generate_draft.py --force` … pending が残っていても追加生成

## ⚠️ 運用ルール（重要）
- **PR表記は必須**（ステマ規制）。アフィ投稿には自動で付くが、手動投稿時も必ず付ける。
- プロフィール文にも「※投稿にはアフィリエイト広告（PR）を含みます」を入れておく（二重開示）。
- **薬機法**に注意：育毛・美白・痩身などの効果断定は書かない。「清潔感」「印象」など体感ベースで。PERSONA / SYSTEM_PROMPT で制御済み。
- 女性蔑視・ナンパ自慢・他者を見下す表現はNG（PERSONA で制御済み）。
- 同一文面の連投は X のスパム判定対象。PR文面・本文ともランダム生成で分散している。
