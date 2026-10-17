import csv, sys
from pathlib import Path
sys.path.insert(0, "scripts"); import tracker
rows = [
 ("2026-10-17","saramin","101","서비스기획","알파소프트","","","https://example.invalid/jobs/101"),
 ("2026-10-17","saramin","102","사업기획","베타체불(주)","","","https://example.invalid/jobs/102"),
 ("2026-10-17","saramin","103","서비스기획","감마러닝","","","https://example.invalid/jobs/103"),
 ("2026-10-17","jobkorea","104","사업기획","델타커머스","","","https://example.invalid/jobs/104"),
]
with open("data/postings.tsv","w",encoding="utf-8",newline="") as f:
    w = csv.writer(f, delimiter="\t"); w.writerow(["first_seen","site","id","title","company","deadline","condition","url"]); w.writerows(rows)
tracker.save([{"id":"001","date":"2026-10-10","site":"saramin","company":"알파소프트","title":"서비스기획","url":rows[0][7],"score":"4.1","verdict":"지원","status":"평가함","followup_count":"0"}])
Path("data/blacklist.md").write_text("| 회사 | 범위 | 날짜 | 사유 |\n|---|---|---|---|\n| 베타체불 | company | 2026-03-01 | 임금체불 |\n", encoding="utf-8")
