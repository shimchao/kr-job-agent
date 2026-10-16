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
def saramin_url(keyword, page):
    q = urllib.parse.urlencode({
        "searchType": "search", "searchword": keyword,
        "recruitPage": page, "recruitSort": "relation", "recruitPageCount": 20,
    })
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
            "condition": "",
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
    ap.add_argument("--dry", action="store_true", help="파일에 저장하지 않고 보기만")
    a = ap.parse_args()

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
    new, skipped, stopped = [], [], set()

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
