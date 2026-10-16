#!/usr/bin/env python3
"""공고가 아직 열려 있는지 확인한다 (평가 전에 먼저 돌린다).

실행 예:
  python3 scripts/liveness.py "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55296971"

출력 한 줄: `ACTIVE|근거`  `CLOSED|근거`  `UNKNOWN|근거` · 종료 코드 0/1/2
판정 규칙:
- CLOSED: 주소가 404/410 이거나, 본문에 '마감된 공고·접수가 마감·채용이 마감·삭제된 공고' 같은 명시 문구가 있을 때만.
- ACTIVE: 제목에 D-숫자 · '채용시 마감'·'상시채용' · 접수기간 안의 날짜가 보일 때.
- 그 외는 UNKNOWN — 추측으로 닫힘/열림을 판정하지 않는다. (원본 career-ops 와 같은 원칙: 증거 없이 마감 단정 금지)
지키는 것: robots.txt 거절 시 UNKNOWN 으로 끝낸다. 로그인·지원은 하지 않는다.
"""
import re
import sys
import urllib.error
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robots_guard import RobotsGuard, polite_get  # noqa: E402

CLOSED_PAT = re.compile(r"마감된\s*공고|접수가\s*마감|채용이\s*마감|채용\s*마감되었|삭제된\s*공고|존재하지\s*않는\s*공고|종료된\s*공고|접수\s*종료")
ACTIVE_PAT = re.compile(r"\(D-\d+\)|D-\d+|채용시\s*마감|상시\s*채용|오늘마감|D-Day")


def classify(text):
    m = CLOSED_PAT.search(text)
    if m:
        return "CLOSED", f"본문 문구: '{m.group(0)}'"
    m = ACTIVE_PAT.search(text)
    if m:
        return "ACTIVE", f"본문 표시: '{m.group(0)}'"
    return "UNKNOWN", "열림·마감을 판단할 근거 문구가 없음"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    try:
        text = polite_get(url, RobotsGuard())
    except PermissionError as e:
        print(f"UNKNOWN|{e}"); sys.exit(2)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            print(f"CLOSED|HTTP {e.code}"); sys.exit(1)
        print(f"UNKNOWN|HTTP {e.code}"); sys.exit(2)
    except Exception as e:
        print(f"UNKNOWN|{type(e).__name__}"); sys.exit(2)
    # 화면 위쪽(제목·상단 정보)만 본다 — 아래쪽 '추천 공고' 목록의 문구에 속지 않기 위해
    head = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    head = re.sub(r"<[^>]+>", " ", head)[:6000]
    state, why = classify(head)
    print(f"{state}|{why}")
    sys.exit({"ACTIVE": 0, "CLOSED": 1}.get(state, 2))


if __name__ == "__main__":
    main()
