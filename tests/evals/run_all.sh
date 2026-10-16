#!/bin/bash
# 다섯 케이스를 순서대로(한 번에 하나씩) 돌린다. 사용: tests/evals/run_all.sh [out_dir]
OUT="${1:-/tmp/kr-job-agent-evals}"; D="$(cd "$(dirname "$0")" && pwd)"
for c in p1_good p3_agency p4_inject p5_offtarget p2_trap; do "$D/run_case.sh" "$c" "/job-eval" "$OUT"; done
