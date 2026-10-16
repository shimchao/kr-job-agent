#!/usr/bin/env python3
"""공고 주소 하나의 본문 글자를 읽어 stdout 에 찍는다 (job-eval 이 쓴다).

실행 예:
  python3 scripts/fetch_posting.py "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55296971"
  python3 scripts/fetch_posting.py "https://www.jobkorea.co.kr/Recruit/GI_Read/50131304"

입력: 공고 주소 1개. 출력: 화면 글자(스크립트·스타일 제거) 최대 12,000자.
지키는 것: robots.txt 가 막은 주소·원티드 등 허용 목록 밖 사이트는 읽지 않는다.
하지 않는 것: 로그인, 지원, 이미지 속 글자 읽기(공고가 이미지면 글자가 거의 안 나온다). 상세 본문은 두 사이트 모두 따로 불러오는 방식이라 요약 정보만 읽힐 수 있다(그때 [주의] 문구가 뜬다).
종료 코드 2 = 읽지 못함 → 그때는 사용자가 공고 본문을 직접 붙여 넣는다.
"""
import html
import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robots_guard import RobotsGuard, polite_get  # noqa: E402

ALLOWED_HOSTS = {"www.saramin.co.kr", "www.jobkorea.co.kr"}
MAX = 12000


def to_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in raw.splitlines()]
    return "\n".join(l for l in lines if l)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    host = urllib.parse.urlsplit(url).netloc
    if host not in ALLOWED_HOSTS:
        print(f"[읽지 않음] {host} 는 자동으로 읽는 사이트가 아닙니다. 공고 본문을 붙여 넣어 주세요.")
        sys.exit(2)
    try:
        text = to_text(polite_get(url, RobotsGuard()))
    except PermissionError as e:
        print(f"[읽지 않음] {e}\n공고 본문을 직접 붙여 넣어 주세요.")
        sys.exit(2)
    except Exception as e:
        print(f"[읽지 못함] {type(e).__name__}: {e}\n공고 본문을 직접 붙여 넣어 주세요.")
        sys.exit(2)
    if len(text) < 200:
        print(f"[본문이 거의 없음: {len(text)}자] 이미지로 된 공고이거나 로그인이 필요한 화면일 수 있습니다. 본문을 직접 붙여 넣어 주세요.")
        sys.exit(2)
    if not re.search(r"담당\s*업무|주요\s*업무|자격\s*요건|지원\s*자격|우대\s*사항|Responsibilit|Qualification", text):
        print("[주의] 요약 정보만 읽혔습니다. 담당업무·자격요건 같은 상세 본문은 화면이 열린 뒤 따로 불러와서 이 도구로는 안 읽힙니다.\n"
              "      평가 정확도를 위해 공고 상세 본문을 복사해 붙여 넣어 주세요.\n")
    print(text[:MAX])
    if len(text) > MAX:
        print(f"\n[잘림: 전체 {len(text)}자 중 {MAX}자만 출력]")


if __name__ == "__main__":
    main()
