#!/usr/bin/env python3
"""지원 현황표(data/tracker.tsv) 관리 — 추가·상태변경·목록·통계·팔로업 시점·제외 회사 확인.

실행 예:
  python3 scripts/tracker.py add --site saramin --company 테스트(주) --title "사업기획" --url URL --score 4.2 --verdict 지원 --report data/reports/001-x.md
  python3 scripts/tracker.py set-status 3 지원함
  python3 scripts/tracker.py list [--status 지원함]
  python3 scripts/tracker.py stats
  python3 scripts/tracker.py followups [--applied-days 7]
  python3 scripts/tracker.py check-blacklist --company 테스트(주) [--url URL]

규칙: 같은 공고(사이트+번호, 없으면 회사+제목)는 두 번 추가하지 않고 기존 줄을 갱신한다.
      id 는 한 번 정하면 바뀌지 않는다. 표를 손으로 고치지 않고 이 도구로만 바꾼다.
하지 않는 것: 지원서 제출, 외부 전송. 모든 값은 이 PC 의 data/ 에만 저장.
"""
import argparse
import csv
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "data" / "tracker.tsv"
BLACKLIST = ROOT / "data" / "blacklist.md"
COLS = ["id", "date", "site", "company", "title", "url", "score", "verdict", "status",
        "report", "applied_date", "last_followup", "followup_count", "notes"]
STATUSES = ["평가함", "지원서 준비", "지원함", "서류 통과", "과제·테스트", "면접", "오퍼", "입사 결정",
            "탈락", "지원 안 함", "마감", "무응답 종료"]
ACTIVE = {"지원함": 7, "서류 통과": 1, "과제·테스트": 1, "면접": 1}  # 첫 팔로업까지 일수 (원본 규칙)
REPEAT = {"지원함": 7, "서류 통과": 3, "과제·테스트": 3, "면접": 3}   # 이후 간격


def norm(s):
    s = (s or "").lower()
    s = re.sub(r"\(주\)|（주）|㈜|\(유\)|\(재\)|주식회사|유한회사|유한책임회사", "", s)  # 법인 표기를 먼저 지운다
    return re.sub(r"[\s\-_·.,()（）\[\]]", "", s)


def key_of(url):
    m = re.search(r"saramin\.co\.kr.*rec_idx=(\d+)", url or "")
    if m:
        return ("saramin", m.group(1))
    m = re.search(r"jobkorea\.co\.kr/Recruit/GI_Read/(\d+)", url or "")
    if m:
        return ("jobkorea", m.group(1))
    return None


def load():
    if not TSV.exists():
        return []
    with TSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save(rows):
    TSV.parent.mkdir(exist_ok=True)
    with TSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def find_dup(rows, url, company, title):
    k = key_of(url)
    for r in rows:
        if k and key_of(r["url"]) == k:
            return r
    for r in rows:
        if norm(r["company"]) == norm(company) and norm(r["title"]) == norm(title) and norm(company):
            return r
    return None


def cmd_add(a):
    rows = load()
    dup = find_dup(rows, a.url, a.company, a.title)
    if dup:
        for f in ("score", "verdict", "report", "notes"):
            v = getattr(a, f)
            if v:
                dup[f] = v
        dup["date"] = dup["date"] or date.today().isoformat()
        save(rows)
        print(f"UPDATED id={dup['id']} (이미 있던 공고 — 새 줄을 만들지 않고 갱신)")
        return
    nid = str(max([int(r["id"]) for r in rows if r["id"].isdigit()] + [0]) + 1).zfill(3)
    rows.append({"id": nid, "date": date.today().isoformat(), "site": a.site, "company": a.company,
                 "title": a.title, "url": a.url, "score": a.score or "", "verdict": a.verdict or "",
                 "status": a.status, "report": a.report or "", "applied_date": "", "last_followup": "",
                 "followup_count": "0", "notes": a.notes or ""})
    save(rows)
    print(f"ADDED id={nid}")


def find(rows, ref):
    for r in rows:
        if r["id"] == ref.zfill(3) or r["id"] == ref:
            return r
    k = key_of(ref)
    for r in rows:
        if k and key_of(r["url"]) == k:
            return r
    return None


def cmd_set(a):
    if a.status not in STATUSES:
        sys.exit(f"상태는 다음 중 하나여야 합니다: {', '.join(STATUSES)}")
    rows = load()
    r = find(rows, a.ref)
    if not r:
        sys.exit(f"'{a.ref}' 를 찾지 못했습니다. `list` 로 id 를 확인하세요.")
    r["status"] = a.status
    if a.status == "지원함" and not r["applied_date"]:
        r["applied_date"] = date.today().isoformat()
    if a.note:
        r["notes"] = (r["notes"] + "; " if r["notes"] else "") + a.note
    save(rows)
    print(f"OK id={r['id']} → {a.status}")


def cmd_list(a):
    rows = [r for r in load() if not a.status or r["status"] == a.status]
    if not rows:
        print("(없음)")
        return
    print("| id | 날짜 | 회사 | 직무 | 점수 | 판단 | 상태 |\n|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['id']} | {r['date']} | {r['company']} | {r['title']} | {r['score']} | {r['verdict']} | {r['status']} |")


def cmd_stats(_):
    rows = load()
    if not rows:
        print("(비어 있음)")
        return
    from collections import Counter
    c = Counter(r["status"] for r in rows)
    print(f"전체 {len(rows)}건")
    for s in STATUSES:
        if c.get(s):
            print(f"- {s}: {c[s]}")
    scored = [float(r["score"]) for r in rows if re.fullmatch(r"\d(\.\d)?", r["score"] or "")]
    if scored:
        print(f"평균 점수 {sum(scored)/len(scored):.1f} (점수 있는 {len(scored)}건 기준)")
    applied = [r for r in rows if r["status"] in ("지원함", "서류 통과", "과제·테스트", "면접", "오퍼", "입사 결정", "탈락", "무응답 종료")]
    if applied:
        passed = [r for r in applied if r["status"] in ("서류 통과", "과제·테스트", "면접", "오퍼", "입사 결정")]
        print(f"지원 {len(applied)}건 중 서류 통과 이상 {len(passed)}건 (※ 표본이 작으면 비율을 해석하지 마세요)")


def cmd_followups(a):
    today, out = date.today(), []
    for r in load():
        st = r["status"]
        if st not in ACTIVE:
            continue
        n = int(r["followup_count"] or 0)
        if st == "지원함" and n >= 2:
            out.append((r, "무응답 종료 후보 — 팔로업 2회 후에도 답이 없음"))
            continue
        base = r["last_followup"] or r["applied_date"] or r["date"]
        try:
            d0 = datetime.strptime(base, "%Y-%m-%d").date()
        except ValueError:
            continue
        gap = (a.applied_days if st == "지원함" else ACTIVE[st]) if not r["last_followup"] else REPEAT[st]
        due = d0 + timedelta(days=gap)
        if due <= today:
            out.append((r, f"팔로업 시점 지남 ({due.isoformat()} 기준, 팔로업 {n}회)"))
    if not out:
        print("지금 팔로업할 곳이 없습니다.")
    for r, why in out:
        print(f"- #{r['id']} {r['company']} / {r['title']} [{r['status']}] — {why}")


def cmd_mark_followup(a):
    rows = load()
    r = find(rows, a.ref)
    if not r:
        sys.exit("찾지 못했습니다.")
    r["last_followup"] = date.today().isoformat()
    r["followup_count"] = str(int(r["followup_count"] or 0) + 1)
    save(rows)
    print(f"OK id={r['id']} 팔로업 {r['followup_count']}회")


def cmd_blacklist(a):
    if not BLACKLIST.exists():
        print("NONE (data/blacklist.md 없음 — 제외 목록을 쓰지 않는 상태)")
        return
    host = re.sub(r"^https?://([^/]+).*", r"\1", a.url or "").lower().rstrip(".")
    for line in BLACKLIST.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("회사", "Company"):
            continue
        name, scope, since, reason = cells[0], cells[1].lower(), cells[2], cells[3]
        if scope == "domain":
            if host and (host == name.lower() or host.endswith("." + name.lower())):
                print(f"HIT|{name}|{since}|{reason}")
                return
        elif norm(name) and norm(name) == norm(a.company):
            print(f"HIT|{name}|{since}|{reason}")
            return
    print("NONE")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    for f in ("site", "company", "title", "url"):
        p.add_argument(f"--{f}", required=True)
    for f in ("score", "verdict", "report", "notes"):
        p.add_argument(f"--{f}")
    p.add_argument("--status", default="평가함", choices=STATUSES)
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("set-status"); p.add_argument("ref"); p.add_argument("status"); p.add_argument("--note"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("list"); p.add_argument("--status"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("stats"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("followups"); p.add_argument("--applied-days", type=int, default=7); p.set_defaults(fn=cmd_followups)
    p = sub.add_parser("mark-followup"); p.add_argument("ref"); p.set_defaults(fn=cmd_mark_followup)
    p = sub.add_parser("check-blacklist"); p.add_argument("--company", required=True); p.add_argument("--url"); p.set_defaults(fn=cmd_blacklist)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
