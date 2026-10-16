# 시작하기 — 처음부터 10분

터미널을 처음 써 보는 분도 따라 할 수 있게 적었습니다. (확인한 환경: macOS. Windows·Linux 는 아래 「Windows 메모」를 보세요.)

## 1. 준비물 3가지
1. **Claude 유료 요금제** (Pro·Max·Team·Enterprise) 또는 Claude Console 계정 — Claude Code 공식 문서 기준입니다.
2. **Claude Code** 설치 (공식 문서 명령, 2026-10-16 확인):
   - macOS·Linux·WSL: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - Homebrew: `brew install --cask claude-code`
   - 설치 후 새 터미널을 열고 `claude --version` 으로 확인합니다. 터미널을 처음 열어 본다면 공식 [터미널 가이드](https://code.claude.com/docs/en/terminal-guide)를 먼저 보세요.
3. **Python 3.9 이상** — 이 도구의 스크립트가 씁니다(설치할 패키지는 없습니다). `python3 --version` 으로 확인합니다.
   (PDF 이력서를 만들려면 Google Chrome 도 있어야 합니다.)

## 2. 이 폴더에서 Claude 열기
```bash
cd 이_폴더_경로
claude
```
처음이면 브라우저로 로그인하라고 나옵니다. 로그인하면 화면 아래에 입력창이 보입니다.

## 3. 첫 설정 (5분)
입력창에 `/job-setup` 을 입력합니다. 이력서는 두 가지 방법으로 줄 수 있습니다.
- **기존 파일 경로**를 알려 주기: docx · hwpx(한글) · pdf · txt 가능. (옛 `.hwp` 는 한글에서 hwpx 나 docx 로 저장해서 주세요.)
- 내용을 **붙여넣기**

그다음 희망 직무·지역·연봉 하한 같은 질문에 답합니다. 끝나면 `cv.md`, `config/profile.yml` 이 만들어집니다. **이 파일들은 이 PC 에만 있고 Git 에 올라가지 않습니다.**

> 🔴 만들어진 `cv.md` 를 한 번 열어 보세요. 숫자·기간·「주도/참여」가 맞는지가 이후 모든 결과의 바탕입니다. 틀린 것은 직접 고치세요. 도구는 이 파일에 없는 사실을 쓰지 않습니다.

## 4. 공고 하나 평가해 보기
사람인·잡코리아·원티드 등에서 공고 **링크 또는 본문**을 복사해 입력창에 `/job-eval` 과 함께 붙여 넣습니다.
- 사람인·잡코리아 링크는 요약 정보만 읽힙니다. 평가가 정확해지려면 **공고 상세 본문도 복사해 붙여 넣으세요.**
- 결과는 `data/reports/` 에 보고서로 저장되고, 대화창에는 「지원/검토/보류/건너뛰기」 판단과 핵심 근거가 나옵니다.

## 5. 이어서 쓰는 순서
`/job-eval` 에서 **지원** 이 나오면 → `/job-apply`(자소서·경력기술서) → `/job-resume`(맞춤 이력서) → 지원은 **직접** 제출 → `/job-track`(현황·팔로업) → 면접이 잡히면 `/job-interview` → 오퍼가 오면 `/job-offer`.
새 공고를 모으고 싶으면 `/job-scan`(사람인·잡코리아 목록)을 씁니다.

## 문제가 생기면
| 증상 | 해결 |
|---|---|
| `/job-` 를 입력해도 스킬이 안 나옴 | 이 폴더(`.claude/skills` 가 있는 곳)에서 `claude` 를 실행했는지 확인 |
| `python3: command not found` | Python 3 설치 후 새 터미널 |
| 공고가 「요약 정보만 읽힘」이라고 나옴 | 정상입니다. 상세 본문을 복사해 붙여 넣으세요 |
| 스캔 결과가 0건 | 사이트가 막았거나 화면 구조가 바뀐 것입니다. 이유가 「못 가져온 것」에 나옵니다. 링크 붙여넣기로 대체하세요 |
| 웹 검색 허용을 묻는 창이 뜸 | 회사·연봉 조사에 필요합니다. 허용하지 않아도 평가는 되며 「확인 불가」로 표시됩니다 |

## Windows 메모
스크립트는 macOS 에서 검증했습니다. Windows 에서는 `python3` 대신 `python` 을 쓰는 경우가 있어 스킬이 부르는 명령이 안 맞을 수 있습니다(WSL 권장). PDF 생성은 크롬 경로가 달라 동작하지 않을 수 있으며, 그때는 HTML 파일이 만들어지니 브라우저에서 「인쇄 → PDF로 저장」을 쓰세요.
