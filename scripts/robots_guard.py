"""robots.txt 검사기 (표준 라이브러리만 사용).

파이썬 기본 urllib.robotparser 는 경로 안의 `*` 와 `$` 를 처리하지 못해
사람인 같은 사이트 규칙을 잘못 읽는다. 그래서 규칙 해석을 직접 한다.

규칙 해석 (RFC 9309):
- 내 UA 이름이 들어 있는 그룹이 있으면 그 그룹만, 없으면 `*` 그룹을 쓴다.
- 가장 긴 규칙이 이긴다. 길이가 같으면 Allow 가 이긴다.
- robots.txt 를 못 읽으면(403 등) **막힌 것으로 본다** (안전 쪽).
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request

UA_NAME = "kr-job-agent"
USER_AGENT = f"{UA_NAME}/0.1 (personal use; runs locally on the user's PC)"


def _fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def _pattern(path):
    # robots 경로 패턴 -> 정규식. `*` = 아무 글자, 끝의 `$` = 끝 고정
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in path)
    return re.compile("^" + rx + ("$" if anchored else ""))


class RobotsRules:
    def __init__(self, text=None, blocked_all=False):
        self.blocked_all = blocked_all
        self.rules = []  # (길이, allow?, 정규식)
        if text is not None:
            self._parse(text)

    def _parse(self, text):
        groups = []  # [(agents, [(allow, path)])]
        agents, rules, last_was_agent = [], [], False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = [s.strip() for s in line.split(":", 1)]
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent:
                    if agents:
                        groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(val.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if val == "" and key == "disallow":
                    continue  # 빈 Disallow = 전부 허용
                rules.append((key == "allow", val))
            else:
                last_was_agent = False
        if agents:
            groups.append((agents, rules))

        mine = [g for g in groups if any(UA_NAME in a for a in g[0])]
        chosen = mine or [g for g in groups if "*" in g[0]]
        for _, rs in chosen:
            for allow, path in rs:
                if path:
                    self.rules.append((len(path), allow, _pattern(path)))

    def allowed(self, url):
        if self.blocked_all:
            return False
        p = urllib.parse.urlsplit(url)
        target = p.path + (("?" + p.query) if p.query else "")
        best = None  # (길이, allow)
        for length, allow, rx in self.rules:
            if rx.match(target):
                if best is None or length > best[0] or (length == best[0] and allow):
                    best = (length, allow)
        return True if best is None else best[1]


class RobotsGuard:
    """사이트별 robots.txt 를 한 번만 받아 캐시한다."""

    def __init__(self):
        self._cache = {}
        self.reasons = {}

    def _load(self, host_url):
        if host_url in self._cache:
            return self._cache[host_url]
        try:
            with _fetch(host_url + "/robots.txt") as r:
                text = r.read().decode("utf-8", errors="ignore")
            rules = RobotsRules(text)
        except urllib.error.HTTPError as e:
            rules = RobotsRules(blocked_all=True)
            self.reasons[host_url] = f"robots.txt 응답 {e.code} — 규칙을 읽지 못해 막힌 것으로 처리"
        except Exception as e:  # 네트워크 오류 등
            rules = RobotsRules(blocked_all=True)
            self.reasons[host_url] = f"robots.txt 조회 실패({type(e).__name__}) — 막힌 것으로 처리"
        self._cache[host_url] = rules
        return rules

    def check(self, url):
        p = urllib.parse.urlsplit(url)
        host = f"{p.scheme}://{p.netloc}"
        ok = self._load(host).allowed(url)
        return ok, ("" if ok else self.reasons.get(host, "robots.txt 가 이 경로를 막고 있음"))


def polite_get(url, guard, delay=3.0, timeout=20, _last=[0.0]):
    """robots 검사 → 간격 두기 → 요청. 막히면 예외. 403/429 가 오면 재시도하지 않는다."""
    ok, why = guard.check(url)
    if not ok:
        raise PermissionError(f"robots.txt 금지: {url} ({why})")
    wait = delay - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    with _fetch(url, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="ignore")
