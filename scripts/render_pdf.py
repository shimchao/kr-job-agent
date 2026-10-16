#!/usr/bin/env python3
"""마크다운 이력서를 인쇄용 HTML 과 PDF 로 만든다 (표준 라이브러리 + 설치된 크롬).

실행 예:
  python3 scripts/render_pdf.py data/applications/2026-10-16_회사_직무/이력서-맞춤.md

입력: 마크다운 파일. 출력: 같은 폴더에 .html 과 .pdf (크롬이 없으면 .html 만).
지원하는 마크다운: # ## ### 제목, - 목록, **굵게**, 빈 줄 문단, --- 구분선. 표·이미지는 지원하지 않는다.
하지 않는 것: 내용 수정, 외부 전송. 모든 처리는 이 PC 안에서 이루어진다.
"""
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: 'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif; font-size: 10.5pt; line-height: 1.5; color: #111; }
h1 { font-size: 20pt; margin: 0 0 4pt; } h2 { font-size: 12.5pt; border-bottom: 1px solid #333; padding-bottom: 2pt; margin: 14pt 0 6pt; }
h3 { font-size: 11pt; margin: 9pt 0 3pt; } ul { margin: 2pt 0 6pt; padding-left: 16pt; } li { margin: 1.5pt 0; }
p { margin: 3pt 0; } hr { border: 0; border-top: 1px solid #bbb; margin: 8pt 0; }
"""


def inline(s):
    s = html.escape(s)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def md_to_html(md):
    out, in_ul, para = [], False, []

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para = []

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    for line in md.splitlines():
        if line.strip().startswith("<!--"):
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            flush_para(); close_ul()
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"^\s*[-*]\s+", line):
            flush_para()
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif re.match(r"^-{3,}\s*$", line):
            flush_para(); close_ul(); out.append("<hr>")
        elif not line.strip():
            flush_para(); close_ul()
        else:
            close_ul(); para.append(line.strip())
    flush_para(); close_ul()
    return "\n".join(out)


def find_chrome():
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(c).exists():
            return c
    for n in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(n)
        if p:
            return p
    return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    body = md_to_html(src.read_text(encoding="utf-8"))
    page = f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(src.stem)}</title><style>{CSS}</style></head><body>\n{body}\n</body></html>'
    h = src.with_suffix(".html")
    h.write_text(page, encoding="utf-8")
    print(f"HTML: {h}")
    chrome = find_chrome()
    if not chrome:
        print("크롬을 찾지 못해 PDF 는 만들지 못했습니다. HTML 을 브라우저로 열어 '인쇄 → PDF로 저장'을 쓰세요.")
        return
    pdf = src.with_suffix(".pdf")
    r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", h.resolve().as_uri()], capture_output=True, text=True, timeout=90)
    if pdf.exists() and pdf.stat().st_size > 0:
        print(f"PDF: {pdf} ({pdf.stat().st_size} bytes) — 열어서 글자 깨짐·페이지 넘침을 확인하세요.")
    else:
        print(f"PDF 생성 실패: {r.stderr.strip()[:300]}")


if __name__ == "__main__":
    main()
