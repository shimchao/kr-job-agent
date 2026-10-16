#!/usr/bin/env python3
"""기존 이력서 파일(docx·hwpx·pdf·txt·md)에서 글자만 뽑아 stdout 에 찍는다 (/job-setup 이 쓴다).

실행 예:
  python3 scripts/extract_text.py ~/Documents/이력서.docx > /tmp/resume.txt
  python3 scripts/extract_text.py ~/Documents/경력기술서.hwpx

지원: .docx · .hwpx(한글 새 형식) · .pdf(pdftotext 가 있으면 그것, 없으면 macOS 기본 PDFKit) · .txt · .md
지원하지 않음: .hwp(옛 한글 형식 — 한글에서 'hwpx 또는 docx 로 저장' 후 다시), 스캔 이미지 PDF(글자가 없음), 표 서식 보존.
출력은 글자뿐이므로 표·서식은 사라진다. 사실 확인은 사람이 한다. 모든 처리는 이 PC 안에서 이루어진다.
종료 코드 2 = 읽지 못함(이유를 stderr 로 알림).
"""
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def docx_text(p):
    with zipfile.ZipFile(p) as z:
        xml = z.read("word/document.xml")
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out = []
    for para in ET.fromstring(xml).iter(ns + "p"):
        out.append("".join(t.text or "" for t in para.iter(ns + "t")))
    return "\n".join(out)


def hwpx_text(p):
    out = []
    with zipfile.ZipFile(p) as z:
        names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n))
        if not names:
            raise ValueError("hwpx 안에서 본문(Contents/section*.xml)을 찾지 못했습니다")
        for n in names:
            root = ET.fromstring(z.read(n))
            for para in root.iter():
                if para.tag.endswith("}p"):
                    out.append("".join((t.text or "") for t in para.iter() if t.tag.endswith("}t")))
    return "\n".join(out)


JXA = r"""
ObjC.import('PDFKit'); ObjC.import('Foundation');
const args = $.NSProcessInfo.processInfo.arguments;
const doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(args.objectAtIndex(args.count-1)));
if (!doc || doc.isNil()) { throw new Error('PDF 를 열지 못함'); }
doc.string.js;
"""


def pdf_text(p):
    if shutil.which("pdftotext"):
        return subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True, check=True).stdout
    if sys.platform == "darwin":
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA, str(p)], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        raise ValueError("PDF 에서 글자를 뽑지 못했습니다(스캔 이미지일 수 있음). 이력서 내용을 붙여 넣어 주세요.")
    raise ValueError("PDF 를 읽을 도구가 없습니다. pdftotext 를 설치하거나 내용을 붙여 넣어 주세요.")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1]).expanduser()
    if not p.exists():
        print(f"파일이 없습니다: {p}", file=sys.stderr); sys.exit(2)
    ext = p.suffix.lower()
    try:
        if ext == ".docx":
            text = docx_text(p)
        elif ext == ".hwpx":
            text = hwpx_text(p)
        elif ext == ".pdf":
            text = pdf_text(p)
        elif ext in (".txt", ".md"):
            text = p.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".hwp":
            print("옛 한글 형식(.hwp)은 읽지 못합니다. 한글에서 '다른 이름으로 저장 → hwpx 또는 docx' 후 다시 주세요.", file=sys.stderr); sys.exit(2)
        else:
            print(f"지원하지 않는 형식: {ext}", file=sys.stderr); sys.exit(2)
    except (zipfile.BadZipFile, ValueError, subprocess.CalledProcessError, KeyError, ET.ParseError) as e:
        print(f"읽지 못했습니다: {e}", file=sys.stderr); sys.exit(2)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 30:
        print("글자가 거의 없습니다(스캔 이미지일 수 있음). 이력서 내용을 붙여 넣어 주세요.", file=sys.stderr); sys.exit(2)
    print(text)


if __name__ == "__main__":
    main()
