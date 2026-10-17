#!/usr/bin/env python3
"""공고 여러 건을 차례로 평가할 때 쓰는 대기열 관리 (data/batch-state.tsv).

실행 예:
  python3 scripts/batch.py queue [--limit 10] [--sites saramin]   # postings.tsv 의 새 공고를 대기열에 올린다
  python3 scripts/batch.py queue --profile                        # config/profile.yml 의 연차·연봉 하한·제목 키워드로 거른다
                                                                  # (제목 키워드로 뺀 공고도 batch-discard.log 에 남는다. 가끔 훑어서 놓친 게 없는지 본다)
  python3 scripts/batch.py queue --exp 8 --min-sal 7000           # 직접 지정 (목록에 적힌 값만 본다. 미표기는 남긴다)
  python3 scripts/batch.py attach 7 --file 공고본문.txt            # 본문을 붙여 넣은 뒤 대기로 되돌린다 (또는 표준입력)
  python3 scripts/batch.py next [--n 3]                           # 대기 중인 공고 n건을 처리 중으로 바꾸고 출력
  python3 scripts/batch.py mark 7 completed --report 004 --score 4.2
  python3 scripts/batch.py mark 7 needs_confirmation --note "헤드헌팅: 경유 회사 확인 필요"
  python3 scripts/batch.py status                                 # 건수와, 확인 대기·실패 항목
  python3 scripts/batch.py requeue --failed                       # 실패한 것만 다시 대기로

상태: pending · processing · completed · failed · skipped · needs_confirmation
- queue 는 이미 현황표에 있는 공고, 제외 목록(data/blacklist.md) 회사, 대기열에 이미 있는 공고를 올리지 않는다.
  걸러낸 것은 skipped 로 남기고 data/batch-discard.log 에 사유를 한 줄씩 적는다(조용히 버리지 않는다).
- 사이트 목록·본문 읽기는 요약만 되는 경우가 많다. 작업자가 본문(담당업무·자격요건)을 못 읽으면 needs_text 로 두고,
  사용자가 본문을 붙여 넣으면(attach) data/inbox/{id}.txt 에 저장하고 대기로 되돌린다. 작업자는 inbox 파일을 먼저 읽는다.
- 같은 공고가 사람인·잡코리아에 같이 있으면(회사+제목이 같음) 한 건만 올리고 나머지는 skipped 로 남긴다.
- needs_confirmation(헤드헌팅·경유 확인)은 requeue 로 되돌리지 않는다. 사용자가 답한 뒤에만 mark 로 닫는다.
- 중단돼도 다시 실행하면 이어진다. processing 으로 남은 것은 `requeue --stale` 로 대기로 돌린다.
하지 않는 것: 공고 읽기·평가·지원. 이 파일은 표만 관리한다.
"""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters  # noqa: E402
import tracker  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTINGS = ROOT / "data" / "postings.tsv"
STATE = ROOT / "data" / "batch-state.tsv"
DISCARD = ROOT / "data" / "batch-discard.log"
COLS = ["id", "site", "company", "title", "url", "status", "updated", "report", "score", "note"]
INBOX = ROOT / "data" / "inbox"
STATUSES = ["pending", "processing", "completed", "failed", "skipped", "needs_confirmation", "needs_text"]


def now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def save(rows):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    tmp.replace(STATE)


def discard(r, why):
    with DISCARD.open("a", encoding="utf-8") as f:
        f.write(f"{now()}\t{r['id']}\t{r['url']}\t{why}\n")


def cmd_queue(a):
    with tracker.locked():
        state = load(STATE)
        have = {(r["site"], r["id"]) for r in state}
        tracked = tracker.load()
        sites = set(a.sites.split(",")) if a.sites else None
        min_exp, min_sal = a.exp, a.min_sal
        title_inc, title_exc = [], []
        if a.profile:
            pr = filters.load_profile()
            min_exp = min_exp if min_exp is not None else pr.get("experience_years")
            min_sal = min_sal if min_sal is not None else (pr.get("min_sal_man") or None)
            title_inc, title_exc = pr.get("title_keywords", []), pr.get("exclude_title_keywords", [])
        seen_keys = {filters.norm_key(r["company"], r["title"]) for r in state if r["status"] != "skipped"}
        added = skipped = 0
        for p in load(POSTINGS):
            if a.limit and added >= a.limit:
                break
            if sites and p["site"] not in sites:
                continue
            if (p["site"], p["id"]) in have:
                continue
            row = {"id": p["id"], "site": p["site"], "company": p["company"], "title": p["title"], "url": p["url"],
                   "status": "pending", "updated": now(), "report": "", "score": "", "note": ""}
            why = None
            if title_inc and filters.title_ok(p["title"], title_inc, title_exc) is False:
                why = "제목이 목표 직무 키워드와 맞지 않음(제목 키워드 판정, 본문은 안 봄)"
            elif min_exp is not None and filters.exp_ok(p["condition"], min_exp) is False:
                why = f"경력 요건이 {min_exp}년과 맞지 않음: {p['condition']}"
            elif min_sal is not None and filters.sal_ok(p["condition"], min_sal) is False:
                why = f"목록 연봉이 {min_sal}만원 미만: {p['condition']}"
            elif filters.norm_key(p["company"], p["title"]) in seen_keys:
                why = "다른 사이트에 같은 공고가 이미 대기열에 있음"
            elif tracker.find_dup(tracked, p["url"], p["company"], p["title"]):
                why = "이미 현황표에 있는 공고"
            else:
                bl = tracker.blacklist_hit(p["company"], p["url"])
                if bl and bl.startswith("HIT"):
                    why = "제외 목록: " + bl.split("|", 3)[-1]
            if why:
                row["status"], row["note"] = "skipped", why
                discard(row, why)
                skipped += 1
            else:
                added += 1
                seen_keys.add(filters.norm_key(p["company"], p["title"]))
                unknown = [n for n, v in (("연차", filters.exp_ok(p["condition"], min_exp) if min_exp is not None else True),
                                          ("연봉", filters.sal_ok(p["condition"], min_sal) if min_sal is not None else True)) if v is None]
                if unknown:
                    row["note"] = "목록에 " + "·".join(unknown) + " 미표기 — 본문에서 확인"
            state.append(row)
            have.add((p["site"], p["id"]))
        save(state)
    print(f"대기열에 {added}건 올림, {skipped}건 제외(사유는 data/batch-discard.log)")


def cmd_next(a):
    with tracker.locked():
        state = load(STATE)
        out = [r for r in state if r["status"] == "pending"][: a.n]
        for r in out:
            r["status"], r["updated"] = "processing", now()
        save(state)
    if not out:
        print("대기 중인 공고가 없습니다.")
    for r in out:
        print("\t".join([r["id"], r["site"], r["company"], r["title"], r["url"]]))


def cmd_mark(a):
    if a.status not in STATUSES:
        sys.exit(f"상태는 {', '.join(STATUSES)} 중 하나")
    with tracker.locked():
        state = load(STATE)
        hits = [r for r in state if r["id"] == a.ref]
        if len(hits) != 1:
            sys.exit(f"id {a.ref}: {len(hits)}건 일치 — 하나여야 합니다")
        r = hits[0]
        r["status"], r["updated"] = a.status, now()
        for k in ("report", "score", "note"):
            v = getattr(a, k)
            if v is not None:
                r[k] = v
        if a.status == "skipped":  # 사전 선별로 뺀 것도 사유를 남긴다
            discard(r, r["note"] or "사유 미기재")
        save(state)
    print(f"OK {a.ref} → {a.status}")


def cmd_status(a):
    state = load(STATE)
    if not state:
        print("(대기열 비어 있음)")
        return
    from collections import Counter
    c = Counter(r["status"] for r in state)
    print(f"전체 {len(state)}건: " + " · ".join(f"{s} {c[s]}" for s in STATUSES if c.get(s)))
    for r in state:
        if r["status"] in ("needs_confirmation", "needs_text", "failed"):
            print(f"- [{r['status']}] #{r['id']} {r['company']} / {r['title']} — {r['note']} ({r['url']})")


def cmd_attach(a):
    text = Path(a.file).read_text(encoding="utf-8") if a.file else sys.stdin.read()
    if len(text.strip()) < 200:
        sys.exit("본문이 너무 짧습니다(200자 미만). 담당업무·자격요건·우대사항까지 복사해 주세요.")
    with tracker.locked():
        state = load(STATE)
        hits = [r for r in state if r["id"] == a.ref]
        if len(hits) != 1:
            sys.exit(f"id {a.ref}: {len(hits)}건 일치 — 하나여야 합니다")
        INBOX.mkdir(parents=True, exist_ok=True)
        (INBOX / f"{a.ref}.txt").write_text(text, encoding="utf-8")
        hits[0]["status"], hits[0]["updated"], hits[0]["note"] = "pending", now(), "본문 붙여 넣음 (data/inbox)"
        save(state)
    print(f"OK {a.ref}: data/inbox/{a.ref}.txt 저장, 대기로 되돌림")


def cmd_requeue(a):
    with tracker.locked():
        state = load(STATE)
        n = 0
        for r in state:
            if (a.failed and r["status"] == "failed") or (a.stale and r["status"] == "processing"):
                r["status"], r["updated"] = "pending", now()
                n += 1
        save(state)
    print(f"{n}건을 대기로 되돌림 (needs_confirmation 은 되돌리지 않음)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("queue"); p.add_argument("--limit", type=int, default=0); p.add_argument("--sites")
    p.add_argument("--exp", type=int, help="내 연차. 목록의 경력 범위에 안 들면 제외"); p.add_argument("--min-sal", type=int, help="연봉 하한(만원). 목록 연봉이 이보다 낮으면 제외")
    p.add_argument("--profile", action="store_true", help="config/profile.yml 의 연차·연봉 하한을 쓴다"); p.set_defaults(fn=cmd_queue)
    p = sub.add_parser("attach"); p.add_argument("ref"); p.add_argument("--file"); p.set_defaults(fn=cmd_attach)
    p = sub.add_parser("next"); p.add_argument("--n", type=int, default=1); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("mark"); p.add_argument("ref"); p.add_argument("status")
    for k in ("report", "score", "note"):
        p.add_argument(f"--{k}")
    p.set_defaults(fn=cmd_mark)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("requeue"); p.add_argument("--failed", action="store_true"); p.add_argument("--stale", action="store_true"); p.set_defaults(fn=cmd_requeue)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
