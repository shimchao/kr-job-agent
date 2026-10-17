#!/usr/bin/env python3
"""공고 목록의 「조건」 칸(사람인 목록 글자)에서 경력 범위·연봉을 읽는 공용 함수.

목록에 적힌 글자만 읽는다. 적혀 있지 않으면 None(미표기)이고, 「없다」로 바꾸지 않는다.
프로필(config/profile.yml)의 연차·연봉 하한을 읽는 함수도 여기에 둔다.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def exp_range(cond):
    """(최소, 최대) 연차. 경력무관·신입경력 = (0, 99). 읽을 수 없으면 None."""
    c = cond or ""
    m = re.search(r"경력\s*(\d+)\s*~\s*(\d+)년", c)
    if m:
        return int(m[1]), int(m[2])
    m = re.search(r"경력\s*(\d+)년\s*↑", c)
    if m:
        return int(m[1]), 99
    m = re.search(r"경력\s*(\d+)년\s*↓", c)
    if m:
        return 0, int(m[1])
    if "경력무관" in c or "신입·경력" in c:
        return 0, 99
    if re.search(r"(^|\s)신입(\s|$)", c) and "경력" not in c:
        return 0, 0  # 신입만 받는 공고 (연차를 가진 사람에게는 해당 없음)
    return None


def salary_man(cond):
    """목록에 적힌 연봉(만원). 없으면 None."""
    m = re.search(r"([\d,]+)\s*만원", cond or "")
    return int(m[1].replace(",", "")) if m else None


def exp_ok(cond, years):
    """True/False, 목록에 연차가 없으면 None(확인 필요)."""
    r = exp_range(cond)
    if r is None:
        return None
    return r[0] <= years <= r[1]


def sal_ok(cond, min_man):
    """True/False, 목록에 연봉이 없으면 None(미표기 — 평가 때 본문에서 확인)."""
    s = salary_man(cond)
    if s is None:
        return None
    return s >= min_man


def load_profile():
    """config/profile.yml 에서 필요한 값만 읽는다(PyYAML 없이). 없으면 빈 dict."""
    p = ROOT / "config" / "profile.yml"
    if not p.exists():
        return {}
    out, in_salary, in_list = {}, False, None
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.split("#")[0].rstrip()
        m = re.match(r"^(title_keywords|exclude_title_keywords):\s*$", s)
        if m:
            in_list = m[1]
            out[in_list] = []
            continue
        if in_list and re.match(r"^\s+-\s+\S", s):
            out[in_list].append(re.sub(r"^\s+-\s+", "", s).strip())
            continue
        if in_list and s and not s.startswith(" "):
            in_list = None
        if re.match(r"^salary:\s*$", s):
            in_salary = True
            continue
        if in_salary and re.match(r"^\s+min_annual_krw:\s*(\d+)", s):
            out["min_sal_man"] = int(re.match(r"^\s+min_annual_krw:\s*(\d+)", s)[1]) // 10000
            continue
        if s and not s.startswith(" "):
            in_salary = False
        m = re.match(r"^experience_years:\s*(\d+)", s)
        if m:
            out["experience_years"] = int(m[1])
    return out


def title_ok(title, include, exclude=()):
    """제목이 목표 직무 키워드를 하나라도 포함하고 제외 키워드가 없으면 True. include 가 비어 있으면 판단하지 않는다(None)."""
    t = (title or "").lower().replace(" ", "")
    if any(x.lower().replace(" ", "") in t for x in exclude):
        return False
    if not include:
        return None
    return any(k.lower().replace(" ", "") in t for k in include)


def norm_key(company, title):
    """사이트가 달라도 같은 공고로 묶기 위한 열쇠(법인 표기·공백·특수문자 제거)."""
    def n(x):
        x = re.sub(r"\(주\)|（주）|㈜|\(유\)|주식회사|유한회사", "", (x or "").lower())
        x = re.sub(r"채용|모집|공고|합니다|담당자|담당", "", x)
        return re.sub(r"[\s\-_·.,()（）\[\]/·]", "", x)
    return n(company) + "|" + n(title)
