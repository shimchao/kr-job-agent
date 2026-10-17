#!/usr/bin/env python3
"""지원 현황표(data/tracker.tsv)를 한 장짜리 HTML(data/dashboard.html)로 만든다.

실행: python3 scripts/dashboard.py [--out data/dashboard.html]
읽기만 한다. 표를 고치지 않고 어디에도 보내지 않는다. 외부 스크립트·글꼴을 불러오지 않는다(이 PC 안에서만 열림).
공고·회사 이름은 공고 본문에서 온 값이라 모두 HTML 이스케이프한다.
"""
import argparse
import html
import re
from collections import Counter
from pathlib import Path

import tracker

ROOT = Path(__file__).resolve().parent.parent
STAGES = ["평가함", "지원서 준비", "지원함", "서류 통과", "과제·테스트", "면접", "오퍼", "입사 결정"]
CLOSED = ["탈락", "지원 안 함", "마감", "무응답 종료"]


def e(x):
    return html.escape(str(x or ""))


def build(rows, due, deadlines=()):
    c = Counter(r["status"] for r in rows)
    bars = "".join(
        f'<div class="bar"><span>{e(s)}</span><i style="width:{c[s] * 100 // max(1, max(c.values()))}%"></i><b>{c[s]}</b></div>'
        for s in STAGES + CLOSED if c.get(s)
    )
    scored = [float(r["score"]) for r in rows if re.fullmatch(r"\d(\.\d)?", r["score"] or "")]
    avg = f"{sum(scored) / len(scored):.1f}" if scored else "-"
    n_apply = sum(1 for r in rows if r["status"] in STAGES[2:] + ["탈락", "무응답 종료"])
    note = "표본이 작습니다. 비율은 해석하지 말고 건수로만 보세요." if n_apply < 10 else ""
    due_rows = "".join(
        f"<tr><td>#{e(r['id'])}</td><td>{e(r['company'])}</td><td>{e(r['title'])}</td><td>{e(r['status'])}</td><td>{e(why)}</td></tr>"
        for r, why in due
    ) or '<tr><td colspan="5">지금 팔로업할 곳이 없습니다.</td></tr>'
    dl_rows = "".join(
        f"<tr><td>#{e(r['id'])}</td><td>{e(r['company'])}</td><td>{e(r['title'])}</td><td>{e(r['status'])}</td>"
        f"<td>{d.isoformat()} ({'오늘' if left == 0 else (str(abs(left)) + '일 지남' if left < 0 else 'D-' + str(left))})</td></tr>"
        for r, d, left in deadlines
    ) or '<tr><td colspan="5">7일 안에 마감되는 미지원 공고가 없습니다.</td></tr>'
    body = "".join(
        f"<tr><td>#{e(r['id'])}</td><td>{e(r['company'])}</td><td>{e(r['title'])}</td><td>{e(r['score'])}</td>"
        f"<td>{e(r['verdict'])}</td><td>{e(r['status'])}</td><td>{e(r['applied_date'])}</td><td>{e(r['notes'])}</td></tr>"
        for r in rows
    ) or '<tr><td colspan="8">현황표가 비어 있습니다.</td></tr>'
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>지원 현황</title>
<style>
:root{{--bg:#fff;--fg:#1f2328;--mut:#6b7280;--line:#e5e7eb;--acc:#2563eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#16181d;--fg:#e6e8eb;--mut:#9aa3af;--line:#2b2f37;--acc:#7aa2ff}}}}
body{{margin:0 auto;max-width:1000px;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
h1{{font-size:20px}} h2{{font-size:16px;margin-top:28px}} .mut{{color:var(--mut)}}
.kpi{{display:flex;gap:24px;flex-wrap:wrap}} .kpi div{{min-width:90px}} .kpi b{{font-size:24px;display:block}}
.bar{{display:grid;grid-template-columns:90px 1fr 32px;gap:8px;align-items:center;margin:4px 0}}
.bar i{{display:block;height:10px;background:var(--acc);border-radius:3px}} .bar b{{text-align:right}}
table{{border-collapse:collapse;width:100%}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
.wrap{{overflow-x:auto}}
</style>
<h1>지원 현황</h1>
<div class="kpi"><div><b>{len(rows)}</b>전체 공고</div><div><b>{n_apply}</b>지원 이후</div><div><b>{avg}</b>평균 점수</div><div><b>{len(due)}</b>팔로업 대상</div></div>
<p class="mut">{e(note)}</p>
<h2>단계별 건수</h2>{bars or '<p class="mut">없음</p>'}
<h2>마감 임박 (지원 전)</h2><div class="wrap"><table><tr><th>id</th><th>회사</th><th>직무</th><th>상태</th><th>마감</th></tr>{dl_rows}</table></div>
<h2>지금 팔로업할 곳</h2><div class="wrap"><table><tr><th>id</th><th>회사</th><th>직무</th><th>상태</th><th>사유</th></tr>{due_rows}</table></div>
<h2>전체 현황표</h2><div class="wrap"><table><tr><th>id</th><th>회사</th><th>직무</th><th>점수</th><th>판단</th><th>상태</th><th>지원일</th><th>비고</th></tr>{body}</table></div>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "dashboard.html"))
    a = ap.parse_args()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = tracker.load()
    out.write_text(build(rows, tracker.due_followups(), tracker.upcoming_deadlines()), encoding="utf-8")
    print(f"OK {out} ({len(rows)}건)")


if __name__ == "__main__":
    main()
