#!/bin/bash
# 평가 하나를 격리된 임시 폴더에서 실제 Claude 로 돌린다.
# 사용: tests/evals/run_case.sh p1_good "/job-eval" [out_dir]
# 출력: <out_dir>/<케이스>/ 에 claude 응답(response.txt)과 만들어진 data/ 가 남는다.
set -euo pipefail
CASE="$1"; PROMPT="$2"; OUT="${3:-/tmp/kr-job-agent-evals}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
W="$OUT/$CASE"; rm -rf "$W"; mkdir -p "$W"
/usr/bin/rsync -a --exclude .git --exclude tests --exclude 'data/*' "$REPO/" "$W/"
mkdir -p "$W/data"
/bin/cp "$REPO/tests/evals/fixtures/cv.md" "$W/cv.md"
/bin/cp "$REPO/tests/evals/fixtures/profile.yml" "$W/config/profile.yml"
FIX="$REPO/tests/evals/fixtures"
cd "$W"
# 케이스에 .seed.py 가 있으면 시작 전에 data/ 를 채운다 (예: 날짜가 걸린 현황표)
[ -f "$FIX/$CASE.seed.py" ] && python3 "$FIX/$CASE.seed.py"
# 케이스에 .prompt 가 있으면 그 전문을 쓴다 (공고 평가가 아닌 스킬용)
if [ -f "$FIX/$CASE.prompt" ]; then FULL="$(cat "$FIX/$CASE.prompt")"; else
FULL="$PROMPT

아래는 사용자가 붙여 넣은 공고 본문입니다 (링크 없음).
---
$(cat "$FIX/$CASE.txt")
---"; fi
perl -e 'alarm 900; exec @ARGV' -- "${CLAUDE_BIN:-claude}" -p "$FULL" --permission-mode acceptEdits --allowedTools "Bash(python3:*) Read Write Edit Glob Grep WebSearch WebFetch" > "$W/response.txt" 2> "$W/stderr.txt" || echo "exit $?" >> "$W/stderr.txt"
echo "done $CASE -> $W"
