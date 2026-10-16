import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from robots_guard import RobotsRules  # noqa: E402
from scan import parse_jobkorea, parse_saramin  # noqa: E402
import liveness, tracker, keyword_match, render_pdf, calc, extract_text  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
