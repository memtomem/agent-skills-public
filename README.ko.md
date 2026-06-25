# memtomem-skills

*[English → README.md](README.md)*

[Claude](https://claude.com)와 여러 코딩 에이전트에서 사용할 수 있는
설치형 **문서 처리 스킬(skill) 모음**입니다. 각 스킬은 다음을 함께 제공합니다.

- 에이전트가 그대로 따를 수 있는 `SKILL.md` 작업 지침
- 사람이 직접 실행할 수 있는 파이썬 명령줄 스크립트
- 동작을 재현하고 검증하기 위한 참고 문서와 테스트

일반 도구로는 깨지는 문서에서 깔끔하고 구조화된 내용을 뽑아내는 데 초점을
둡니다 — 아래아한글 / 한컴오피스 문서, 정형화되지 않은 PDF, 그리고 단순 읽기로는
구조가 무너지는 오피스 문서(엑셀·워드·파워포인트)를 다룹니다.

## 어떤 스킬을 쓰면 되나?

| 가진 파일 | 사용할 스킬 | 결과 |
|---|---|---|
| 아래아한글 / 한컴오피스 문서(`.hwp` / `.hwpx`) | [`hwp-toolkit`](skills/hwp-toolkit/) | 텍스트 추출, 구조 검사, 또는 원본 양식 레이아웃을 보존한 채워진 사본 |
| 표, 다단, 스캔, 차트가 섞인 실제 업무용 PDF | [`pdf-parser`](skills/pdf-parser/) | 깔끔한 Markdown, JSON 요소 트리, 렌더링 이미지, 필요한 페이지의 비전 전사 자리표시자 |
| 정돈되지 않은 스프레드시트(`.xlsx` / `.xlsm`) — 표 여러 개, 첫 행이 아닌 헤더, 병합 셀, 수식, 차트 | [`xlsx-parser`](skills/xlsx-parser/) | Markdown + JSON 요소 트리, 병합 셀은 HTML로, 차트 데이터는 XML에서 복원 |
| 워드 문서(`.docx`) — 본문 사이에 표, 중첩 표, 텍스트 상자, 변경 내용 추적 | [`docx-parser`](skills/docx-parser/) | 본문 순서대로 Markdown + JSON, 병합 셀은 HTML로, 텍스트 상자 복원 |
| 파워포인트 덱(`.pptx`) — 슬라이드, 표, 차트, 발표자 노트 | [`pptx-parser`](skills/pptx-parser/) | 읽기 순서대로 Markdown + JSON, 차트 데이터는 XML에서, 발표자 노트 포함 |

스킬은 [`skills/`](skills/) 아래에 계속 추가됩니다.

## 가장 빠른 시작

### 1. Claude Code / Claude Desktop / Cowork에 설치

저장소 루트에서 필요한 스킬만 복사합니다.

```bash
mkdir -p ~/.claude/skills
cp -R skills/hwp-toolkit ~/.claude/skills/    # .hwp / .hwpx용
cp -R skills/pdf-parser  ~/.claude/skills/    # PDF용
cp -R skills/xlsx-parser ~/.claude/skills/    # .xlsx / .xlsm용
cp -R skills/docx-parser ~/.claude/skills/    # .docx용
cp -R skills/pptx-parser ~/.claude/skills/    # .pptx용
```

앱이 `.skill` 패키지 가져오기를 지원한다면 패키지 파일을 빌드해 설치해도 됩니다.

```bash
uv run python scripts/build_all.py            # 모든 dist/<name>.skill 빌드
```

그다음 원하는 `dist/<name>.skill`을 앱의 **Save skill** 또는 스킬 가져오기
기능으로 설치합니다.

### 2. 자연어로 요청

설치 후에는 파일과 원하는 결과를 같이 말하면 됩니다.

- "`application.hwp`에서 표를 포함해 텍스트를 추출해줘."
- "이 한글 `.hwp` 양식에서 강좌명과 강사명을 채워줘."
- "`report.pdf`를 표는 표로 유지하면서 Markdown으로 변환해줘."
- "이 정돈 안 된 `sales.xlsx`에서 시트별 표를 전부 뽑아줘."
- "이 `contract.docx`를 표와 텍스트 상자까지 유지해 Markdown으로 변환해줘."
- "이 `deck.pptx`에서 슬라이드 본문과 표·차트 데이터, 발표자 노트까지 정리해줘."

에이전트가 알맞은 스킬을 읽고 스크립트를 실행한 뒤, 추출 결과나 새 편집본을
돌려줍니다. 원본 문서는 덮어쓰지 않는 흐름을 기본으로 합니다.

### 3. Codex, Cursor, 그 밖의 셸 실행 가능한 에이전트에서 사용

각 스킬에는 일반 파이썬 명령줄 도구가 `scripts/` 폴더에 들어 있습니다.
`.skill` 패키지를 직접 지원하지 않는 에이전트에서는 스킬 폴더나 스크립트를
프로젝트에 복사한 뒤, 그 스킬의 `SKILL.md` 플레이북을 참고하도록 알려주면 됩니다.

- **hwp-toolkit** — [`SKILL.md`](skills/hwp-toolkit/SKILL.md) · [`README.md`](skills/hwp-toolkit/README.md)
- **pdf-parser** — [`SKILL.md`](skills/pdf-parser/SKILL.md) · [`README.md`](skills/pdf-parser/README.md)
- **xlsx-parser** — [`SKILL.md`](skills/xlsx-parser/SKILL.md) · [`README.md`](skills/xlsx-parser/README.md)
- **docx-parser** — [`SKILL.md`](skills/docx-parser/SKILL.md) · [`README.md`](skills/docx-parser/README.md)
- **pptx-parser** — [`SKILL.md`](skills/pptx-parser/SKILL.md) · [`README.md`](skills/pptx-parser/README.md)

## 직접 실행 예시

에이전트가 아니라 사람이 직접 스크립트를 돌릴 때는 아래 흐름을 씁니다.

```bash
# hwp-toolkit
cd skills/hwp-toolkit/scripts
python hwp_extract.py FILE.hwp
python hwp_inspect.py FILE.hwp --paragraphs
python hwp_edit.py replace IN.hwp OUT.hwp --pair "OLD" "NEW"

# pdf-parser
cd ../../pdf-parser/scripts
python pdf_triage.py INPUT.pdf
python pdf_parse.py INPUT.pdf -o OUTDIR

# xlsx-parser / docx-parser / pptx-parser (파싱 -> OUTDIR/INPUT.md + INPUT.json)
cd ../../xlsx-parser/scripts && python xlsx_parse.py INPUT.xlsx -o OUTDIR
cd ../../docx-parser/scripts && python docx_parse.py INPUT.docx -o OUTDIR
cd ../../pptx-parser/scripts && python pptx_parse.py INPUT.pptx -o OUTDIR
```

새 체크아웃에서 직접 스크립트를 쓰려면 먼저 개발 의존성을 설치하세요.

```bash
uv venv
uv pip install -r requirements-dev.txt
```

## 기여자용 확인 명령

```bash
uv run pytest -q
uv run python scripts/build_all.py
```

테스트 픽스처는 테스트가 처음부터 생성합니다. 비공개 문서, 고객 파일, 생성된
바이너리 픽스처는 커밋하지 마세요.

## 바로가기

**hwp-toolkit**

- 사용 가이드: [`README.ko.md`](skills/hwp-toolkit/README.ko.md) · [문제 해결](skills/hwp-toolkit/README.ko.md#문제-해결) · [.hwp와 .hwpx 차이](skills/hwp-toolkit/README.ko.md#두-포맷의-차이)
- 영문 가이드: [`README.md`](skills/hwp-toolkit/README.md) · 작업 지침: [`SKILL.md`](skills/hwp-toolkit/SKILL.md)

**pdf-parser**

- 사용 가이드: [`README.ko.md`](skills/pdf-parser/README.ko.md) · 영문 가이드: [`README.md`](skills/pdf-parser/README.md)
- 작업 지침: [`SKILL.md`](skills/pdf-parser/SKILL.md) · 포맷 내부 구조: [`references/pdf_internals.md`](skills/pdf-parser/references/pdf_internals.md)

**xlsx-parser**

- 사용 가이드: [`README.ko.md`](skills/xlsx-parser/README.ko.md) · 영문 가이드: [`README.md`](skills/xlsx-parser/README.md)
- 작업 지침: [`SKILL.md`](skills/xlsx-parser/SKILL.md) · 포맷 내부 구조: [`references/xlsx_internals.md`](skills/xlsx-parser/references/xlsx_internals.md)

**docx-parser**

- 사용 가이드: [`README.ko.md`](skills/docx-parser/README.ko.md) · 영문 가이드: [`README.md`](skills/docx-parser/README.md)
- 작업 지침: [`SKILL.md`](skills/docx-parser/SKILL.md) · 포맷 내부 구조: [`references/docx_internals.md`](skills/docx-parser/references/docx_internals.md)

**pptx-parser**

- 사용 가이드: [`README.ko.md`](skills/pptx-parser/README.ko.md) · 영문 가이드: [`README.md`](skills/pptx-parser/README.md)
- 작업 지침: [`SKILL.md`](skills/pptx-parser/SKILL.md) · 포맷 내부 구조: [`references/pptx_internals.md`](skills/pptx-parser/references/pptx_internals.md)

## 라이선스

[MIT](LICENSE) © 2026 memtomem
