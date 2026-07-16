#!/bin/bash
# launchd から呼ばれる: 生成 → 推敲 → 投稿の一気通貫
# - X_LIVE_POST=true のときだけ実投稿(pipeline.py 内で判定)
# - pending に既にあれば既存ドラフトを使う(generate は skip)

set -uo pipefail

# 注意: Desktop/Documents/Downloads配下はmacOS TCCでlaunchd実行不可。~/直下に置くこと。
ROOT="/Users/user/x-automation-ikemen"
PY="$ROOT/venv/bin/python3"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/auto_tweet.log"

ts() { date '+%Y-%m-%dT%H:%M:%S%z'; }
echo "[$(ts)] === auto_tweet start ===" >> "$LOG"

# 0. bot判定回避: 毎回0〜35分(0〜2100秒)のランダム遅延で投稿時刻をばらつかせる
JITTER=$(( RANDOM % 2101 ))
echo "[$(ts)] random jitter: sleep ${JITTER}s (~$(( JITTER / 60 ))min)" >> "$LOG"
sleep "$JITTER"
echo "[$(ts)] jitter done, proceeding" >> "$LOG"

# 0.5 スリープ復帰直後はWiFi未接続で Anthropic API が Connection error になる。
#      api.anthropic.com に到達できるまで最大3分待つ(10秒間隔×18回)。
for i in $(seq 1 18); do
  if curl -sS -o /dev/null --max-time 5 https://api.anthropic.com/ 2>/dev/null; then
    echo "[$(ts)] network ready (try $i)" >> "$LOG"
    break
  fi
  echo "[$(ts)] waiting for network (try $i)" >> "$LOG"
  sleep 10
done

# 1. 新規ドラフトを生成(pending に何もない場合のみ)。Connection error 等に備え最大3回再試行。
G_RC=1
for attempt in 1 2 3; do
  "$PY" "$ROOT/scripts/generate_draft.py" >> "$LOG" 2>&1
  G_RC=$?
  [ "$G_RC" -eq 0 ] && break
  echo "[$(ts)] generate_draft.py failed rc=$G_RC (attempt $attempt)" >> "$LOG"
  [ "$attempt" -lt 3 ] && sleep 30
done
echo "[$(ts)] generate_draft.py rc=$G_RC" >> "$LOG"

# 2. pending を推敲して投稿(X_LIVE_POST=true なら本番、false ならドライラン)
"$PY" "$ROOT/scripts/pipeline.py" >> "$LOG" 2>&1
P_RC=$?
echo "[$(ts)] pipeline.py rc=$P_RC" >> "$LOG"

echo "[$(ts)] === auto_tweet end ===" >> "$LOG"
exit 0
