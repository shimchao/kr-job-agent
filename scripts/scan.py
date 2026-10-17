#!/usr/bin/env python3
"""사람인·잡코리아 공고 목록을 가져와 data/postings.tsv 에 쌓는다.

실행 예:
  python3 scripts/scan.py                      # config/search.txt 의 검색어로 두 사이트 1페이지씩
  python3 scripts/scan.py --keywords "사업기획,AI 기획" --pages 2 --sites saramin

지키는 것:
- 사이트 robots.txt 가 막은 주소는 요청하지 않는다 (scripts/robots_guard.py).
- 요청 사이이 3초 이상 쉰다. 403/429 가 오면 그 사이트는 바로 멈춘다.
- 브라우저인 척하지 않는다. 이름표(User-Agent)에 도구 이름을 그대로 적는다.
- 로그인·지원·이력서 경로는 건드리지 않는다. 공개된 검색 목록만 읽는다.
- 가져온 것은 내 PC 의 data/ 에만 저장한다.

하지 않는 것: 상세 본문 수집, 지원, 로그인, 원티드(robots.txt 를 읽을 수 없어 제외).
출력: 새로 발견한 공고를 표로 stdout 에 찍고, data/postings.tsv 에 한 줄씩 추가한다.
"""
import argparse
import csv
import html
import re
import sys
import urllib.error
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robots_guard import RobotsGuard, polite_get  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "data" / "postings.tsv"
COLS = ["first_seen", "site", "id", "title", "company", "deadline", "condition", "url"]


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


# ── 사람인 ─────────────────────────────────────────────
# 사람인 검색 화면의 연봉 필터 코드 (2026-10-17 화면 sal_min_sel 에서 읽은 값). 만원 단위 → 코드
SARAMIN_SAL = {2400: 8, 2600: 9, 2800: 10, 3000: 11, 3200: 12, 3400: 13, 3600: 14, 3800: 15,
               4000: 16, 5000: 17, 6000: 18, 7000: 19, 8000: 20, 9000: 21, 10000: 22}
SAL_MIN = None  # --sal-min 으로 정해진다 (사람인만)


def saramin_url(keyword, page):
    params = {
        "searchType": "search", "searchword": keyword,
        "recruitPage": page, "recruitSort": "relation", "recruitPageCount": 20,
    }
    if SAL_MIN:
        params["sal_min"] = SARAMIN_SAL[SAL_MIN]
    q = urllib.parse.urlencode(params)
    return "https://www.saramin.co.kr/zf_user/search/recruit?" + q


def parse_saramin(text):
    out = []
    for blk in re.split(r'<div class="item_recruit"', text)[1:]:
        m = re.match(r'\s*value="(\d+)"', blk)
        if not m:
            continue
        rid = m.group(1)
        t = re.search(r'<h2 class="job_tit">.*?<a[^>]*title="([^"]*)"', blk, re.S)
        c = re.search(r'<strong class="corp_name">.*?<a[^>]*>(.*?)</a>', blk, re.S)
        d = re.search(r'<span class="date">(.*?)</span>', blk, re.S)
        cond = re.search(r'<div class="job_condition">(.*?)</div>', blk, re.S)
        out.append({
            "id": rid,
            "title": _clean(t.group(1)) if t else "",
            "company": _clean(c.group(1)) if c else "",
            "deadline": _clean(d.group(1)) if d else "",
            "condition": _clean(cond.group(1)).replace("  ", " | ") if cond else "",
            "url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={rid}",
        })
    return out


# ── 잡코리아 ───────────────────────────────────────────
def jobkorea_url(keyword, page):
    q = urllib.parse.urlencode({"stext": keyword, "tabType": "recruit", "Page_No": page})
    return "https://www.jobkorea.co.kr/Search/?" + q


REGION = re.compile(r"^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|전국|해외)")


def _jobkorea_condition(seg, title_html):
    """검색 카드 한 장에서 지역과 경력 구분(신입/경력)만 읽는다. 연차 숫자·연봉은 카드에 없다(본문에서만).
    카드 글자는 「제목 | 회사 | 지역 | 직무들 | … | 경력 또는 신입」 순서로 나온다."""
    i = seg.find(title_html)
    if i < 0:
        return ""
    flat = re.sub(r"<[^>]+>", "|", seg[i:])
    chunk = flat.split("|스크랩|")[0] if "|스크랩|" in flat else flat
    toks = [_clean(t) for t in chunk.split("|") if _clean(t)]
    region = next((t for t in toks[2:5] if REGION.match(t)), "")
    tail = toks[3:]
    if "경력" in tail and "신입 지원 가능" in tail:
        career = "신입·경력"
    elif "경력" in tail:
        career = "경력"
    elif "신입" in tail:
        career = "신입"
    else:
        career = ""
    ym = re.search(r"(\d+)\s*년\s*(이상|↑)", _clean(title_html))  # 제목에 「(5년 이상)」 처럼 적힌 연차
    if ym:
        career = f"경력{ym[1]}년↑"
    return " ".join(x for x in (region, career) if x)


def parse_jobkorea(text):
    """잡코리아 검색 결과는 화면 전용 클래스명이 자주 바뀐다.
    공고 번호(GI_Read/숫자)를 기준으로 묶고, 제목은 굵은 글씨 링크에서 읽는다."""
    out, seen = [], set()
    for m in re.finditer(r'href="https://www\.jobkorea\.co\.kr/Recruit/GI_Read/(\d+)[^"]*"', text):
        rid = m.group(1)
        if rid in seen:
            continue
        seen.add(rid)
        seg = text[m.start(): m.start() + 6000]
        title = re.search(r'<span class="truncate[^"]*font-semibold[^"]*">(.*?)</span>', seg, re.S)
        if not title:
            continue  # 로고 링크 등 제목 없는 항목은 건너뜀
        comp = re.findall(r'alt="([^"]*?) 로고"', seg)  # 로고 링크가 제목 링크보다 앞에 있다
        out.append({
            "id": rid,
            "title": _clean(title.group(1)),
            "company": _clean(comp[0]) if comp else "",
            "deadline": "",
            "condition": _jobkorea_condition(seg, title.group(0)),
            "url": f"https://www.jobkorea.co.kr/Recruit/GI_Read/{rid}",
        })
    return out


SITES = {
    "saramin": (saramin_url, parse_saramin),
    "jobkorea": (jobkorea_url, parse_jobkorea),
}


def read_lines(path):
    if not path.exists():
        return []
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]


def load_seen():
    if not TSV.exists():
        return set()
    with TSV.open(encoding="utf-8") as f:
        return {(r["site"], r["id"]) for r in csv.DictReader(f, delimiter="\t")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keywords", help="쉼표로 구분. 없으면 config/search.txt")
    ap.add_argument("--sites", default="saramin,jobkorea")
    ap.add_argument("--pages", type=int, default=1, help="검색어당 페이지 수 (기본 1, 최대 5)")
    ap.add_argument("--delay", type=float, default=3.0, help="요청 간격(초). 3 미만은 3으로 올림")
    ap.add_argument("--sal-min", type=int, help="사람인 연봉 필터(만원): 2400·2600·…·5000·6000·7000·8000·9000·10000. 잡코리아는 필터가 없어 적용 안 됨")
    ap.add_argument("--profile", action="store_true", help="config/profile.yml 의 연봉 하한을 사람인 연봉 필터로 쓴다(--sal-min 이 없을 때)")
    ap.add_argument("--dry", action="store_true", help="파일에 저장하지 않고 보기만")
    a = ap.parse_args()

    global SAL_MIN
    if a.profile and not a.sal_min:
        import filters
        want = filters.load_profile().get("min_sal_man")
        if want:
            ok = [k for k in SARAMIN_SAL if k <= want]
            if ok:
                a.sal_min = max(ok)  # 하한 이하 중 가장 가까운 사람인 단계(필터는 더 넓게, 이후 목록 연봉으로 다시 거른다)
                print(f"[프로필] 연봉 하한 {want}만원 → 사람인 필터 {a.sal_min}만원 이상")
    if a.sal_min:
        if a.sal_min not in SARAMIN_SAL:
            sys.exit(f"--sal-min 은 {sorted(SARAMIN_SAL)} 중 하나")
        SAL_MIN = a.sal_min
    kws = [k.strip() for k in a.keywords.split(",")] if a.keywords else read_lines(ROOT / "config" / "search.txt")
    if not kws:
        sys.exit("검색어가 없습니다. config/search.txt 에 한 줄에 하나씩 쓰거나 --keywords 로 주세요.")
    excl = [e.lower() for e in read_lines(ROOT / "config" / "exclude.txt")]
    pages, delay = min(max(a.pages, 1), 5), max(a.delay, 3.0)
    sites = [s.strip() for s in a.sites.split(",") if s.strip()]
    for s in sites:
        if s not in SITES:
            sys.exit(f"지원하지 않는 사이트: {s} (지원: {', '.join(SITES)})")

    guard, seen, today = RobotsGuard(), load_seen(), date.today().isoformat()
    new, skipped, stopped, hits = [], [], set(), []

    for site in sites:
        build, parse = SITES[site]
        for kw in kws:
            for pg in range(1, pages + 1):
                if site in stopped:
                    break
                url = build(kw, pg)
                try:
                    text = polite_get(url, guard, delay=delay)
                except PermissionError as e:
                    skipped.append(f"{site}: {e}")
                    stopped.add(site)
                    break
                except urllib.error.HTTPError as e:
                    skipped.append(f"{site}: HTTP {e.code} — 이 사이트는 여기서 멈춤")
                    stopped.add(site)
                    break
                except Exception as e:
                    skipped.append(f"{site}: {type(e).__name__} — {kw} {pg}쪽 건너뜀")
                    continue
                rows = parse(text)
                if not rows:
                    skipped.append(f"{site}: '{kw}' {pg}쪽에서 공고 0건 — 화면 구조가 바뀌었거나 결과가 없음")
                    break
                for r in rows:
                    key = (site, r["id"])
                    if SAL_MIN and site == "saramin" and not any(e in r["title"].lower() for e in excl):
                        if all(h["id"] != r["id"] for h in hits):
                            hits.append({"first_seen": today, "site": site, **r})
                    if key in seen:
                        continue
                    seen.add(key)
                    if any(e in r["title"].lower() for e in excl):
                        continue
                    new.append({"first_seen": today, "site": site, **r})

    if new and not a.dry:
        TSV.parent.mkdir(exist_ok=True)
        fresh = not TSV.exists()
        with TSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
            if fresh:
                w.writeheader()
            w.writerows(new)

    if SAL_MIN and hits:
        out = ROOT / "data" / f"postings-sal{SAL_MIN}.tsv"
        if not a.dry:
            out.parent.mkdir(exist_ok=True)
            with out.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
                w.writeheader()
                w.writerows(hits)
        print(f"## 사람인 연봉 {SAL_MIN}만원 이상 필터 결과 {len(hits)}건 (이미 본 공고 포함)" + (f" → {out.name}" if not a.dry else " (저장 안 함: --dry)"))
        print("※ 사람인 필터는 엄격하지 않아 연봉 미표기·7천 미만이 섞입니다. 조건 칸에 적힌 연봉으로 다시 확인하세요.")
        print("| 회사 | 제목 | 마감 | 조건 | 링크 |\n|---|---|---|---|---|")
        for r in hits:
            print(f"| {r['company']} | {r['title']} | {r['deadline']} | {r['condition']} | {r['url']} |")
        print()
    print(f"## 새 공고 {len(new)}건" + (" (저장 안 함: --dry)" if a.dry else ""))
    if new:
        print("| 사이트 | 회사 | 제목 | 마감 | 조건 | 링크 |\n|---|---|---|---|---|---|")
        for r in new:
            print(f"| {r['site']} | {r['company']} | {r['title']} | {r['deadline']} | {r['condition']} | {r['url']} |")
    if skipped:
        print("\n## 못 가져온 것")
        for s in skipped:
            print(f"- {s}")
    print("\n원티드는 robots.txt 를 읽을 수 없어 자동 스캔에서 제외했습니다. 공고 링크나 본문을 직접 붙여 넣어 주세요.")


if __name__ == "__main__":
    main()
