import sys, csv
from datetime import date, timedelta
sys.path.insert(0, "scripts"); import tracker
d = lambda n: (date.today() - timedelta(days=n)).isoformat()
rows = [
 dict(id="1", date=d(12), site="saramin", company="알파소프트", title="서비스기획", url="", score="4.2", verdict="지원", status="지원함", report="", applied_date=d(10), last_followup="", followup_count="0", notes=""),
 dict(id="2", date=d(6), site="jobkorea", company="베타러닝", title="사업기획", url="", score="4.5", verdict="지원", status="서류 통과", report="", applied_date=d(5), last_followup="", followup_count="0", notes=""),
 dict(id="3", date=d(30), site="saramin", company="감마커머스", title="서비스기획", url="", score="4.0", verdict="지원", status="지원함", report="", applied_date=d(28), last_followup=d(10), followup_count="2", notes=""),
 dict(id="4", date=d(20), site="saramin", company="델타미디어", title="사업기획", url="", score="4.1", verdict="지원", status="탈락", report="", applied_date=d(18), last_followup="", followup_count="0", notes="서류 탈락"),
]
tracker.save(rows)
