#!/usr/bin/env python3
"""공고 본문의 핵심 단어가 내 이력서(cv.md)에 얼마나 들어 있는지 점검한다 — 참고용 진단.

실행 예:
  python3 scripts/keyword_match.py data/reports/001-x.md            # 보고서에 붙은 '공고 원문' 구간 사용
  python3 scripts/keyword_match.py --jd jd.txt --cv cv.md --top 25

입력: 공고 본문(파일), 이력서(기본 cv.md). 출력: 있음/부족/없음 목록과 커버율.
한계: 단어 빈도로 뽑는 단순 방식이라 '핵심 요구사항'과 다를 수 있다. 판정이 아니라 점검용이다.
      🔴 '없음' 단어는 **실제로 한 경험일 때만** 이력서에 넣는다. 없는 경험을 단어만 맞춰 쓰지 않는다.
"""
import argparse
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP = set("""및 등 또는 있는 있음 가능 우대 필수 경력 신입 이상 이하 관련 업무 담당 채용 모집 지원 자격 요건 조건 근무 회사 팀 기타
한 수 위한 통해 대한 대해 하는 하며 합니다 입니다 있습니다 경우 내용 사항 해당 같은 보유 능력 경험 사용 진행 개발 운영 수행 중 및 게시일 화면 없음 포함 적용 상시 최고 이상 가능 연봉 급여 계약형태 회사 근무지 접수 기간 마감 협의 별도 the and for with of to in a an or""".split())


def tokens(text):
    out = re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,}|[가-힣]{2,}", text)
    res = []
    for t in out:
        # 한국어 조사 꼬리 단순 제거
        t2 = re.sub(r"(으로|에서|에게|하고|하여|까지|부터|이다|으로서|에는|에서의|의|을|를|은|는|이|가|와|과|도|에|로)$", "", t) if re.match(r"[가-힣]", t) and len(t) > 2 else t
        if len(t2) >= 2 and t2.lower() not in STOP:
            res.append(t2)
    return res


def jd_from_report(path):
    t = Path(path).read_text(encoding="utf-8")
    m = re.search(r"##\s*(?:공고 원문|Job Description)[^\n]*\n(.*)", t, re.S)
    body = m.group(1) if m else t
    return re.sub(r"^\s*(게시일|Posted)\s*:[^\n]*\n", "", body)  # 우리가 붙인 머리줄은 공고 내용이 아니다


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", nargs="?")
    ap.add_argument("--jd")
    ap.add_argument("--cv", default=str(ROOT / "cv.md"))
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    if not (a.report or a.jd):
        ap.error("보고서 경로 또는 --jd 파일이 필요합니다")
    jd = Path(a.jd).read_text(encoding="utf-8") if a.jd else jd_from_report(a.report)
    cvp = Path(a.cv)
    if not cvp.exists():
        raise SystemExit("cv.md 가 없습니다. /job-setup 을 먼저 하세요.")
    cv = cvp.read_text(encoding="utf-8").lower()
    freq = Counter(t.lower() for t in tokens(jd))
    top = [w for w, _ in freq.most_common(a.top)]
    present = [w for w in top if w in cv]
    thin = [w for w in present if cv.count(w) == 1]
    missing = [w for w in top if w not in cv]
    pct = round(100 * len(present) / len(top)) if top else 0
    print(f"## 키워드 점검 (공고 상위 {len(top)}개 단어 기준) — 이력서 {pct}% 포함")
    print(f"- 충분: {', '.join(w for w in present if w not in thin) or '—'}")
    print(f"- 한 번만 나옴: {', '.join(thin) or '—'}")
    print(f"- 이력서에 없음: {', '.join(missing) or '—'}")
    print("\n※ 단어 빈도 기반의 참고용 점검입니다. '없음' 단어는 실제로 한 경험일 때만 보강하세요.")


if __name__ == "__main__":
    main()
