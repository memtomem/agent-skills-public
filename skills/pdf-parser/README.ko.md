# pdf-parser (한국어 가이드)

*[English guide → README.md](README.md)*

본문, 다단 레이아웃, 괘선·무괘선 표, 차트, 인포그래픽, 스캔 페이지, 삽입
이미지가 뒤섞인 **정형화되지 않은 PDF**를 깔끔한 **Markdown**과 구조화된
**JSON** 요소 트리로 변환하는 Claude 스킬입니다. 한국어+영어를 지원합니다.

## 왜 필요한가

실제 보고서에 `pdftotext`를 돌리면 단(column)이 뒤섞이고, 표가 사라지고,
차트는 아무것도 남지 않습니다. 이 스킬은 대신 **페이지마다 분류(triage)**해서
가장 잘 읽는 추출기로 보내고, 로컬 라이브러리가 정말로 볼 수 없는 부분(스캔
페이지, 데이터가 픽셀 안에 들어 있는 차트)에서만 비전(vision) 모델로
넘깁니다. 비전 경로는 tesseract 한국어 언어 팩 없이 한국어 OCR도 처리합니다.

## 설치

### Claude Code / Claude Desktop / Cowork

스킬 폴더를 스킬 디렉터리에 넣으면 에이전트가 자동으로 인식합니다:

```bash
# 모든 프로젝트에서 사용 (권장)
cp -R pdf-parser ~/.claude/skills/

# 또는 특정 프로젝트에만
cp -R pdf-parser <프로젝트>/.claude/skills/
```

(또는 `python scripts/build_all.py pdf-parser`로 `dist/pdf-parser.skill`을
빌드해 앱의 **Save skill** 버튼으로 설치합니다.) 설치 후에는 PDF를 언급하기만
하면 — “이 PDF에서 표랑 본문 뽑아줘”, “convert this report.pdf to markdown” —
스킬이 자동으로 동작합니다. `/pdf-parser`로 직접 호출할 수도 있습니다.

### Codex, Cursor, 그 밖의 셸 실행 가능한 에이전트

`scripts/`는 평범한 파이썬 CLI입니다(의존성: `pymupdf`, `pdfplumber`).
`scripts/`를 프로젝트에 복사하고 `pip install pymupdf pdfplumber` 한 뒤,
분류 → 파싱 → 비전 전사 → 검증 플레이북이 담긴 `SKILL.md`를 에이전트에
알려주면 됩니다.

## 작업 흐름

```bash
cd scripts

# 1. 분류 — 각 페이지의 경로와 비전이 필요한 페이지 확인
python pdf_triage.py INPUT.pdf

# 2. 로컬 파싱 -> OUTDIR/INPUT.md + INPUT.json + assets/ + render/
#    비전 페이지는 자동으로 렌더링되어 .md 플레이스홀더에 이미지로 삽입됩니다
python pdf_parse.py INPUT.pdf -o OUTDIR

# 3. 삽입된 render/page_NNN.png를 읽고 플레이스홀더 자리에 전사
#    (더 선명하게 다시 렌더링하려면: --render --pages N --dpi 300)
```

전체 흐름(병합·검증 단계 포함)은 `SKILL.md`를, 페이지 분류 휴리스틱과 JSON
요소 스키마는 `references/pdf_internals.md`를 참고하세요.

## 경로(route)

| 경로 | 의미 | 처리 방식 |
|-------|---------|----------|
| `text` | 깨끗한 텍스트 레이어 | PyMuPDF, 읽기 순서 |
| `mixed` | 본문 + 도형 / 다단 | 본문 + 이미지 추출 |
| `table` | 괘선 표가 주를 이룸 | pdfplumber / camelot |
| `scanned` | 텍스트 레이어가 거의 없음 | 렌더링 → 비전 전사 |

## 의존성

PyMuPDF와 pdfplumber가 필수입니다. camelot과 tesseract는 설치되어 있으면
기회적으로 사용합니다. 설치: `pip install pymupdf pdfplumber`.

## 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| 표가 비거나 어긋나게 나옴 | 무괘선 표(그려진 격자가 없는 표)는 의도적으로 로컬에서 감지하지 않습니다 — 해당 페이지를 렌더링(`pdf_parse.py … --render`)해 비전으로 전사하세요. |
| 다단 페이지가 순서가 뒤섞임 | 3단 이상이거나 도형을 감싸는 레이아웃은 순서가 흐트러질 수 있습니다. 분류의 `col` 값을 확인하고 그 페이지는 비전으로 처리하세요. |
| 한국어가 깨져 보임 | 텍스트 레이어가 아니라 이미지로 읽힌 스캔 페이지입니다 — OCR 대신 비전 경로를 쓰세요. |
| `error: … is password-protected` | `--password PASSWORD`를 넘기거나, PDF 뷰어에서 암호를 해제한 뒤 다시 시도하세요. |
| `ModuleNotFoundError: fitz` / `pdfplumber` | `pip install pymupdf pdfplumber` 하고, 스크립트는 `scripts/` 디렉터리에서 실행하세요. |

## 테스트

```bash
python -m pytest tests/pdf_parser/ -q
```

픽스처는 `tests/pdf_parser/fixtures/make_fixtures.py`가 처음부터 생성하며
저장소에 커밋하지 않습니다.
