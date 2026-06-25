# docx-parser (한국어 가이드)

*[English guide → README.md](README.md)*

본문 사이에 표가 끼어 있고, 표 안에 표가 중첩되며, 셀이 병합되고,
글머리·번호 목록, 텍스트 박스, 머리글·바닥글, 변경 내용 추적, 메모가 뒤섞인
**정형화되지 않은 워드 문서**(`.docx`)를 깔끔한 **Markdown**과 구조화된
**JSON** 요소 트리로 변환하는 Claude 스킬입니다. 한국어+영어를 지원합니다.

## 왜 필요한가

`.docx`는 구조화된 XML이지만, 가장 흔한 추출 방식인 `doc.paragraphs` 이어
붙이기는 실제 내용을 조용히 누락하거나 뒤섞습니다. python-docx는 문단과 표를
*별도의* 리스트로 노출하기 때문에, 두 문단 사이에 있던 표는 제자리를
잃습니다. 표는 셀 안에 중첩되고, 셀은 `gridSpan`/`vMerge`로 병합되며, 글머리
목록·텍스트 박스(`w:txbxContent`)·머리글·바닥글·변경 내용 추적·메모는 모두
평면적으로 읽으면 들르지 않는 곳에 들어 있습니다. 이 스킬은 대신 문서를
**본문 순서대로** 순회하여 — 텍스트와 표를 올바르게 번갈아 배치하면서 —
신뢰도 점수와 플래그가 달린 구조화된 요소 트리를 만들어, 위험한 문서가
사람/LLM 확인 대상으로 드러나게 합니다.

## 설치

### Claude Code / Claude Desktop / Cowork

스킬 폴더를 스킬 디렉터리에 넣으면 에이전트가 자동으로 인식합니다. 저장소 루트에서
실행하세요.

```bash
mkdir -p ~/.claude/skills
cp -R skills/docx-parser ~/.claude/skills/
```

이미 `skills/docx-parser/` 안에 있다면 이렇게 실행합니다.

```bash
mkdir -p ~/.claude/skills/docx-parser
cp -R . ~/.claude/skills/docx-parser/
```

특정 프로젝트에만 적용하려면 그 프로젝트의 `.claude/skills/` 아래로 복사하면
됩니다. 패키지 파일을 쓰는 앱이라면 저장소 루트에서 빌드한 뒤 **Save skill**
버튼으로 설치할 수 있습니다.

```bash
uv run python scripts/build_all.py docx-parser
```

설치 후에는 `.docx`를 언급하기만 하면 — “이 워드 문서에서 본문이랑 표 구조
그대로 뽑아줘”, “extract everything from this .docx to markdown keeping
tables” — 스킬이 자동으로 동작합니다. `/docx-parser`로 직접 호출할 수도
있습니다.

### Codex, Cursor, 그 밖의 셸 실행 가능한 에이전트

`scripts/`는 평범한 파이썬 CLI입니다(의존성: `python-docx`. `markitdown`은
선택 사항이며 `--crosscheck`에서만 사용). `scripts/`를 프로젝트에 복사하고
`pip install python-docx` 한 뒤, 파싱 → 플래그 검토 → 검증 플레이북이 담긴
`SKILL.md`를 에이전트에 알려주면 됩니다.

## 작업 흐름

대부분의 사용자는 먼저 에이전트에게 자연어로 요청하면 됩니다.

- “이 워드 문서에서 본문이랑 표 구조 그대로 뽑아줘.”
- “Extract everything from this .docx to markdown keeping tables.”
- “이 계약서 docx를 JSON으로 변환해줘.”
- “이 docx를 마크다운으로 정리해줘 — 표랑 텍스트 박스도 빠뜨리지 말고.”

에이전트가 문서를 본문 순서대로 순회하고, 병합 셀은 HTML로 유지하며, 텍스트
박스를 복원하고, 한 번 더 봐야 할 항목(변경 내용 추적, 중첩 표, 메모)에는
신뢰도 점수와 함께 플래그를 띄웁니다.

명령줄에서 직접 실행할 때는 아래 흐름을 씁니다.

```bash
cd scripts

# 파싱 -> OUTDIR/INPUT.md + INPUT.json
python docx_parse.py INPUT.docx -o OUTDIR

# markitdown 교차 검증 추가 -> OUTDIR/INPUT.markitdown.md 로 비교
python docx_parse.py INPUT.docx -o OUTDIR --crosscheck
```

전체 흐름(출력 형식과 검토 단계)은 `SKILL.md`를, 본문 순서 순회·병합 처리·
신뢰도 모델·JSON 요소 스키마는 `references/docx_internals.md`를 참고하세요.

## 플래그

파서는 사람/LLM 확인이 필요한 문서가 드러나도록 플래그를 띄웁니다. 출력을
신뢰하기 전에 상단 `🔎` 안내와 플래그를 먼저 확인하세요.

| 플래그 | 의미 | 할 일 |
|------|---------|------------|
| `tracked-changes-present` | 문서에 보류 중인 삽입/삭제가 있음 | 텍스트가 현재 마크업을 반영함 — 적용본(accepted)과 원본 중 무엇을 원하는지 정하고 워드에서 확인 |
| `merged-cells` | 표에 `gridSpan`/`vMerge` 병합이 있음 | `<table>` HTML로 렌더링됨 — 병합 범위(span)가 올바른지 확인 |
| `nested-table` | 표 셀 안에 표가 중첩됨 | 구조화된 `nested` 데이터로 보존하고 해당 셀에 HTML로 렌더링 — 내부 행을 점검 |
| `textbox-content` | 텍스트 박스에서 텍스트를 복원함 | `📦 [text box]` 블록으로 렌더링됨 — 누락된 박스가 없는지 확인(복잡한 VML은 더 숨길 수 있음) |
| `comments-present` | 문서에 검토 메모가 있음 | 메모 텍스트가 추출 내용에 포함되어야 하는지 확인 |
| `embedded-images-not-extracted` | 이미지는 개수만 세고 추출하지 않음 | 필요하면 `.docx`(zip)를 열어 `word/media/`에서 가져오기 |
| `needs-vision` | 문서가 *오직* 이미지뿐(텍스트 없음) | 비전 경로로 보내 처리(`needs_vision: true`) |

## 의존성

python-docx가 필수입니다. markitdown은 선택 사항이며, `--crosscheck`가
비교용 second-opinion Markdown을 쓸 때만 사용합니다.

```bash
pip install python-docx          # 필수
pip install markitdown           # 선택, --crosscheck 용
```

## 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| 삽입/삭제가 잘못 보임 | 변경 내용 추적은 *현재* 마크업으로 추출됩니다 — 특정 리비전 상태가 필요하면 워드에서 먼저 적용/거부하세요. |
| 병합 셀 표가 어긋나 보임 | 병합 셀은 GFM이 아니라 `<table>` HTML로 렌더링됩니다 — 행/열 병합 범위가 원본과 일치하는지 확인하세요. |
| 텍스트 박스가 빠진 것 같음 | 텍스트 박스는 `📦 [text box]` 블록으로 추출됩니다. 복잡한 VML / SmartArt는 완전히 드러나지 않을 수 있어 `textbox-content` 플래그가 확인하라고 알려줍니다. |
| 이미지가 안 나옴 | 삽입 이미지는 이번 단계에서 개수만 세고 추출하지 않습니다 — `.docx`(zip)를 열어 `word/media/`에서 원본 파일을 가져오세요. |
| 출력이 비거나 `needs_vision: true` | 텍스트 레이어가 없는 이미지 전용 문서입니다 — 비전 경로로 보내 이미지를 전사하세요. |
| `ModuleNotFoundError: docx` | `pip install python-docx`(임포트 이름은 `docx`) 하고, 스크립트는 `scripts/` 디렉터리에서 실행하세요. |

## 테스트

```bash
python -m pytest tests/docx_parser/ -q
```

픽스처는 `tests/docx_parser/fixtures/make_fixtures.py`가 처음부터 생성하며
저장소에 커밋하지 않습니다.
