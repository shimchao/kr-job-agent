import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from robots_guard import RobotsRules  # noqa: E402
from scan import parse_jobkorea, parse_saramin  # noqa: E402
import liveness, tracker, keyword_match, render_pdf, calc, extract_text, fetch_posting  # noqa: E402
import tempfile, zipfile, io, contextlib

ROBOTS = """
User-agent: GPTBot
Disallow: /

User-agent: *
Disallow: /zf_user/recruit/view/
Disallow: /Click*
Allow: /zf_user/jobs/relay/recruit-view
Disallow: /zf_user/jobs/relay/
Disallow: /*?secret=1$
"""


class Robots(unittest.TestCase):
    def setUp(self):
        self.r = RobotsRules(ROBOTS)

    def test_star_group_used_when_agent_not_named(self):
        self.assertTrue(self.r.allowed("https://x.kr/zf_user/search/recruit?searchword=a"))
        self.assertFalse(self.r.allowed("https://x.kr/zf_user/recruit/view/1"))

    def test_wildcard_prefix(self):
        self.assertFalse(self.r.allowed("https://x.kr/Click123"))

    def test_longest_rule_wins_and_allow_beats_tie(self):
        self.assertTrue(self.r.allowed("https://x.kr/zf_user/jobs/relay/recruit-view?a=1"))
        self.assertFalse(self.r.allowed("https://x.kr/zf_user/jobs/relay/view?a=1"))

    def test_end_anchor(self):
        self.assertFalse(self.r.allowed("https://x.kr/p?secret=1"))
        self.assertTrue(self.r.allowed("https://x.kr/p?secret=12"))

    def test_unreadable_robots_means_blocked(self):
        self.assertFalse(RobotsRules(blocked_all=True).allowed("https://x.kr/"))

    def test_own_agent_group_overrides_star(self):
        r = RobotsRules("User-agent: *\nDisallow: /\n\nUser-agent: kr-job-agent\nDisallow: /private\n")
        self.assertTrue(r.allowed("https://x.kr/open"))
        self.assertFalse(r.allowed("https://x.kr/private/a"))


class Parsers(unittest.TestCase):
    def test_saramin(self):
        html = ('<div class="item_recruit" value="123" data-x="y"><h2 class="job_tit"><a target="_blank" title="사업기획 담당 채용" href="/x"><span>t</span></a></h2>'
                '<div class="job_date"><span class="date">~ 10/30(금)</span></div>'
                '<div class="job_condition"><span>서울</span> <span>경력무관</span></div>'
                '<div class="area_corp"><strong class="corp_name"><a href="/c"> 테스트(주) </a></strong></div></div>')
        r = parse_saramin(html)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["id"], r[0]["title"], r[0]["company"], r[0]["deadline"]),
                         ("123", "사업기획 담당 채용", "테스트(주)", "~ 10/30(금)"))
        self.assertIn("rec_idx=123", r[0]["url"])

    def test_jobkorea_dedup_and_company(self):
        a = '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/77?x=1"><img alt="㈜가나 로고"/></a>'
        b = ('<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/77?x=1"><span class="truncate font-semibold text-a">서비스기획 모집</span></a>')
        r = parse_jobkorea(a + b + a + b)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["id"], r[0]["title"], r[0]["company"]), ("77", "서비스기획 모집", "㈜가나"))

    def test_empty(self):
        self.assertEqual(parse_saramin("<html></html>"), [])
        self.assertEqual(parse_jobkorea("<html></html>"), [])



class Liveness(unittest.TestCase):
    def test_closed_needs_explicit_phrase(self):
        self.assertEqual(liveness.classify("이 공고는 접수가 마감되었습니다")[0], "CLOSED")
        self.assertEqual(liveness.classify("사업기획 채용(D-14) - 사람인")[0], "ACTIVE")
        self.assertEqual(liveness.classify("아무 근거 없는 화면")[0], "UNKNOWN")


class Tracker(unittest.TestCase):
    def test_key_of_and_norm(self):
        self.assertEqual(tracker.key_of("https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55&x=1"), ("saramin", "55"))
        self.assertEqual(tracker.key_of("https://www.jobkorea.co.kr/Recruit/GI_Read/77?a=1"), ("jobkorea", "77"))
        self.assertEqual(tracker.norm("(주) 테스트 컴퍼니"), tracker.norm("테스트컴퍼니"))

    def test_dup_by_url_key_then_company_title(self):
        rows = [{"url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55", "company": "A", "title": "x"}]
        self.assertIsNotNone(tracker.find_dup(rows, "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=55&q=2", "B", "y"))
        self.assertIsNotNone(tracker.find_dup(rows, "https://other/1", "A", "x"))
        self.assertIsNone(tracker.find_dup(rows, "https://other/1", "C", "z"))


class Keywords(unittest.TestCase):
    def test_tokens_drop_stopwords_and_particles(self):
        t = keyword_match.tokens("데이터분석을 통해 SQL 과 Python 우대")
        self.assertIn("SQL", t); self.assertIn("Python", t)
        self.assertNotIn("우대", t)
        self.assertIn("데이터분석", t)



class Render(unittest.TestCase):
    def test_md_to_html(self):
        h = render_pdf.md_to_html("# 제목\n\n- **굵게** 항목\n- 둘째\n\n문단 <b>")
        self.assertIn("<h1>제목</h1>", h)
        self.assertIn("<li><strong>굵게</strong> 항목</li>", h)
        self.assertIn("&lt;b&gt;", h)  # 태그는 이스케이프



class Extract(unittest.TestCase):
    def _zip(self, name, member, xml):
        d = tempfile.mkdtemp(); p = Path(d) / name
        with zipfile.ZipFile(p, "w") as z:
            z.writestr(member, xml)
        return p

    def test_docx(self):
        W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        xml = f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>첫째 줄</w:t></w:r></w:p><w:p><w:r><w:t>둘째 줄</w:t></w:r></w:p></w:body></w:document>'
        self.assertEqual(extract_text.docx_text(self._zip("a.docx", "word/document.xml", xml)), "첫째 줄\n둘째 줄")

    def test_hwpx(self):
        xml = '<hs:sec xmlns:hs="s" xmlns:hp="p"><hp:p><hp:run><hp:t>한글</hp:t></hp:run><hp:run><hp:t>문서</hp:t></hp:run></hp:p></hs:sec>'
        self.assertEqual(extract_text.hwpx_text(self._zip("a.hwpx", "Contents/section0.xml", xml)), "한글문서")


class Calc(unittest.TestCase):
    def run_calc(self, *args):
        buf = io.StringIO()
        old = sys.argv
        sys.argv = ["calc.py", *args]
        try:
            with contextlib.redirect_stdout(buf):
                calc.main()
        finally:
            sys.argv = old
        return buf.getvalue()

    def test_score_rounds_half_up(self):
        self.assertIn("= 1.55 → 1.6", self.run_calc("score", "매치=2", "직무=1", "보상=1", "문화=2", "위험=1"))

    def test_compare_direction(self):
        self.assertIn("8,400 은(는) 7,000보다 큼", self.run_calc("compare", "8400", "7000"))

    def test_annual(self):
        self.assertIn("연 4,200만원", self.run_calc("annual", "350"))


class Batch(unittest.TestCase):
    def setUp(self):
        import batch, csv
        self.batch, self.tmp = batch, tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self._old = (tracker.TSV, tracker.LOCK, tracker.BLACKLIST, batch.POSTINGS, batch.STATE, batch.DISCARD)
        tracker.TSV, tracker.LOCK, tracker.BLACKLIST = t / "tracker.tsv", t / ".lock", t / "blacklist.md"
        batch.POSTINGS, batch.STATE, batch.DISCARD = t / "postings.tsv", t / "batch-state.tsv", t / "discard.log"
        rows = [
            ("2026-10-17", "saramin", "1", "서비스기획", "알파", "", "", "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=1"),
            ("2026-10-17", "saramin", "2", "사업기획", "베타", "", "", "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=2"),
            ("2026-10-17", "saramin", "3", "기획", "감마(주)", "", "", "https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=3"),
            ("2026-10-17", "jobkorea", "4", "운영", "델타", "", "", "https://www.jobkorea.co.kr/Recruit/GI_Read/4"),
        ]
        with batch.POSTINGS.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(batch.COLS if False else ["first_seen", "site", "id", "title", "company", "deadline", "condition", "url"])
            w.writerows(rows)
        tracker.save([{"id": "001", "company": "알파", "title": "서비스기획", "url": rows[0][7], "status": "평가함", "followup_count": "0"}])
        tracker.BLACKLIST.write_text("| 회사 | 범위 | 날짜 | 사유 |\n|---|---|---|---|\n| 감마 | company | 2026-01-01 | 임금체불 |\n", encoding="utf-8")

    def tearDown(self):
        tracker.TSV, tracker.LOCK, tracker.BLACKLIST, self.batch.POSTINGS, self.batch.STATE, self.batch.DISCARD = self._old
        self.tmp.cleanup()

    def run_cmd(self, *argv):
        import argparse
        buf, old = io.StringIO(), sys.argv
        sys.argv = ["batch.py", *argv]
        try:
            with contextlib.redirect_stdout(buf):
                self.batch.main()
        finally:
            sys.argv = old
        return buf.getvalue()

    def states(self):
        return {r["id"]: r["status"] for r in self.batch.load(self.batch.STATE)}

    def test_queue_skips_tracked_and_blacklisted_and_logs(self):
        self.run_cmd("queue")
        self.assertEqual(self.states(), {"1": "skipped", "2": "pending", "3": "skipped", "4": "pending"})
        log = self.batch.DISCARD.read_text(encoding="utf-8")
        self.assertIn("이미 현황표에 있는 공고", log)
        self.assertIn("임금체불", log)

    def test_queue_twice_does_not_duplicate(self):
        self.run_cmd("queue"); self.run_cmd("queue")
        self.assertEqual(len(self.batch.load(self.batch.STATE)), 4)

    def test_next_moves_to_processing_and_resumes(self):
        self.run_cmd("queue")
        out = self.run_cmd("next", "--n", "1")
        self.assertIn("베타", out)
        self.assertEqual(self.states()["2"], "processing")
        self.run_cmd("requeue", "--stale")
        self.assertEqual(self.states()["2"], "pending")

    def test_held_item_is_not_requeued(self):
        self.run_cmd("queue"); self.run_cmd("next", "--n", "2")
        self.run_cmd("mark", "2", "needs_confirmation", "--note", "헤드헌팅")
        self.run_cmd("requeue", "--failed", "--stale")
        self.assertEqual(self.states()["2"], "needs_confirmation")
        self.assertIn("헤드헌팅", self.run_cmd("status"))

    def test_mark_unknown_id_fails(self):
        self.run_cmd("queue")
        with self.assertRaises(SystemExit):
            self.run_cmd("mark", "99", "completed")


    def test_queue_filters_by_exp_and_salary_keep_unknown(self):
        import csv
        rows = [("2026-10-17", "saramin", "11", "기획", "에이", "", "서울 경력10년↑ 정규직 8,000 만원", "u11"),
                ("2026-10-17", "saramin", "12", "기획", "비이", "", "서울 경력 5~10년 정규직 5,000 만원", "u12"),
                ("2026-10-17", "saramin", "13", "기획", "씨이", "", "서울 경력5년↑ 정규직", "u13"),
                ("2026-10-17", "saramin", "14", "기획", "디이", "", "서울 경력5년↑ 정규직 9,000 만원", "u14")]
        with self.batch.POSTINGS.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["first_seen", "site", "id", "title", "company", "deadline", "condition", "url"]); w.writerows(rows)
        self.run_cmd("queue", "--exp", "8", "--min-sal", "7000")
        st = self.states()
        self.assertEqual((st["11"], st["12"], st["13"], st["14"]), ("skipped", "skipped", "pending", "pending"))
        note = {r["id"]: r["note"] for r in self.batch.load(self.batch.STATE)}
        self.assertIn("연봉 미표기", note["13"])
        self.assertEqual(note["14"], "")

    def test_cross_site_duplicate_is_skipped(self):
        import csv
        rows = [("2026-10-17", "saramin", "21", "[가] 신사업 기획", "(주)가나", "", "", "u21"),
                ("2026-10-17", "jobkorea", "22", "[가] 신사업 기획 채용", "㈜가나", "", "", "u22")]
        with self.batch.POSTINGS.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["first_seen", "site", "id", "title", "company", "deadline", "condition", "url"]); w.writerows(rows)
        self.run_cmd("queue")
        self.assertEqual(sorted(self.states().values()), ["pending", "skipped"])

    def test_attach_saves_text_and_requeues(self):
        self.run_cmd("queue"); self.run_cmd("next", "--n", "1")
        self.run_cmd("mark", "2", "needs_text", "--note", "본문 못 읽음")
        self.assertIn("본문 못 읽음", self.run_cmd("status"))
        src = Path(self.tmp.name) / "body.txt"
        src.write_text("담당업무 " * 60, encoding="utf-8")
        self.batch.INBOX = Path(self.tmp.name) / "inbox"
        self.run_cmd("attach", "2", "--file", str(src))
        self.assertEqual(self.states()["2"], "pending")
        self.assertTrue((self.batch.INBOX / "2.txt").exists())
        with self.assertRaises(SystemExit):
            short = Path(self.tmp.name) / "s.txt"; short.write_text("짧음", encoding="utf-8")
            self.run_cmd("attach", "2", "--file", str(short))

    def test_parallel_adds_do_not_lose_rows(self):
        import threading, argparse
        def add(i):
            a = argparse.Namespace(site="x", company=f"c{i}", title=f"t{i}", url=f"u{i}", score="", verdict="", report="", notes="", deadline="", status="평가함")
            with contextlib.redirect_stdout(io.StringIO()):
                tracker.cmd_add(a)
        th = [threading.Thread(target=add, args=(i,)) for i in range(8)]
        [t.start() for t in th]; [t.join() for t in th]
        self.assertEqual(len(tracker.load()), 1 + 8)


class Filters(unittest.TestCase):
    def test_exp_range_and_ok(self):
        import filters
        self.assertEqual(filters.exp_range("서울 경력 3~12년 대졸↑ 정규직"), (3, 12))
        self.assertEqual(filters.exp_range("서울 경력5년↑ 대졸↑"), (5, 99))
        self.assertEqual(filters.exp_range("경력무관"), (0, 99))
        self.assertIsNone(filters.exp_range("서울 경력 대졸↑"))
        self.assertIs(filters.exp_ok("경력10년↑", 8), False)
        self.assertIs(filters.exp_ok("경력 2~10년", 8), True)
        self.assertIsNone(filters.exp_ok("", 8))

    def test_salary_unknown_is_not_low(self):
        import filters
        self.assertIsNone(filters.sal_ok("서울 경력5년↑", 7000))
        self.assertIs(filters.sal_ok("정규직 5,000 만원", 7000), False)
        self.assertIs(filters.sal_ok("정규직 7,000 만원", 7000), True)

    def test_same_posting_across_sites_same_key(self):
        import filters
        a = filters.norm_key("(주)미디어윌네트웍스", "[미디어윌네트웍스] 신사업 발굴 및 기획 담당")
        b = filters.norm_key("㈜미디어윌네트웍스", "[미디어윌네트웍스] 신사업 발굴 및 기획 담당 채용")
        self.assertEqual(a, b)


class JobkoreaCard(unittest.TestCase):
    CARD = ('<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/111?x=1"><img alt="가나㈜ 로고"/></a>'
            '<a href="https://www.jobkorea.co.kr/Recruit/GI_Read/111?x=1"><span class="truncate font-semibold">{t}</span></a>'
            '<div>가나㈜</div><div>서울 마포구</div><div>경영·비즈니스기획</div><div>즉시 지원</div>{tags}<button>스크랩</button>')

    def parse(self, t, tags):
        import scan
        return scan.parse_jobkorea(self.CARD.format(t=t, tags=tags))[0]

    def test_title_years_and_region(self):
        r = self.parse("사업기획 (5년 이상)", "<span>경력</span>")
        self.assertIn("서울 마포구", r["condition"])
        self.assertIn("경력5년↑", r["condition"])

    def test_newcomer_only_is_excluded_for_8_years(self):
        import filters
        r = self.parse("서비스기획 채용", "<span>신입</span>")
        self.assertIs(filters.exp_ok(r["condition"], 8), False)

    def test_no_career_tag_is_unknown_not_excluded(self):
        import filters
        r = self.parse("서비스기획 채용", "")
        self.assertIsNone(filters.exp_ok(r["condition"], 8))


class Deadlines(unittest.TestCase):
    def test_parse_deadline(self):
        from datetime import date
        t = date(2026, 10, 17)
        self.assertEqual(tracker.parse_deadline("~ 10/29(목)", t), date(2026, 10, 29))
        self.assertEqual(tracker.parse_deadline("내일마감", t), date(2026, 10, 18))
        self.assertEqual(tracker.parse_deadline("2026.10.31(토)", t), date(2026, 10, 31))
        self.assertIsNone(tracker.parse_deadline("채용시", t))
        self.assertIsNone(tracker.parse_deadline("상시채용", t))
        self.assertEqual(tracker.parse_deadline("~ 1/5(월)", t), date(2027, 1, 5))

    def test_upcoming_only_unapplied_and_sorted(self):
        from datetime import date, timedelta
        tmp = tempfile.TemporaryDirectory()
        old = tracker.TSV
        tracker.TSV = Path(tmp.name) / "t.tsv"
        d = lambda n: (date.today() + timedelta(days=n)).isoformat()
        try:
            tracker.save([
                {"id": "1", "company": "가", "status": "평가함", "deadline": d(5), "followup_count": "0"},
                {"id": "2", "company": "나", "status": "평가함", "deadline": d(1), "followup_count": "0"},
                {"id": "3", "company": "다", "status": "지원함", "deadline": d(1), "followup_count": "0"},
                {"id": "4", "company": "라", "status": "평가함", "deadline": "채용시", "followup_count": "0"},
                {"id": "5", "company": "마", "status": "평가함", "deadline": d(30), "followup_count": "0"},
            ])
            self.assertEqual([r["id"] for r, _, _ in tracker.upcoming_deadlines(7)], ["2", "1"])
        finally:
            tracker.TSV = old
            tmp.cleanup()


class ScanSalary(unittest.TestCase):
    def test_saramin_salary_filter_code(self):
        import scan
        scan.SAL_MIN = 7000
        try:
            self.assertIn("sal_min=19", scan.saramin_url("사업기획", 1))
        finally:
            scan.SAL_MIN = None
        self.assertNotIn("sal_min", scan.saramin_url("사업기획", 1))


class Dashboard(unittest.TestCase):
    def setUp(self):
        import dashboard
        from datetime import date, timedelta
        self.dashboard, self.tmp = dashboard, tempfile.TemporaryDirectory()
        self._old = tracker.TSV
        tracker.TSV = Path(self.tmp.name) / "tracker.tsv"
        d = lambda n: (date.today() - timedelta(days=n)).isoformat()
        tracker.save([
            {"id": "1", "date": d(10), "company": "<script>x</script>(주)가", "title": "기획", "status": "지원함",
             "applied_date": d(9), "score": "4.2", "followup_count": "0"},
            {"id": "2", "date": d(2), "company": "나", "title": "기획", "status": "지원함",
             "applied_date": d(1), "score": "3.0", "followup_count": "0"},
        ])

    def tearDown(self):
        tracker.TSV = self._old
        self.tmp.cleanup()

    def test_due_followups_only_overdue(self):
        self.assertEqual([r["id"] for r, _ in tracker.due_followups()], ["1"])

    def test_html_escapes_company_and_counts(self):
        out = self.dashboard.build(tracker.load(), tracker.due_followups())
        self.assertNotIn("<script>x", out)
        self.assertIn("&lt;script&gt;x", out)
        self.assertIn("표본이 작습니다", out)

    def test_empty_table_renders(self):
        tracker.save([])
        self.assertIn("현황표가 비어 있습니다", self.dashboard.build([], []))


class DetailUrl(unittest.TestCase):
    def test_saramin_detail_from_rec_idx(self):
        self.assertEqual(fetch_posting.detail_url("https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=123&x=1"),
                         "https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx=123")

    def test_jobkorea_detail_from_gno(self):
        self.assertEqual(fetch_posting.detail_url("https://www.jobkorea.co.kr/Recruit/GI_Read/456?x=1"),
                         "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=456")

    def test_other_site_has_no_detail_url(self):
        self.assertIsNone(fetch_posting.detail_url("https://example.com/job/1"))


if __name__ == "__main__":
    unittest.main()
