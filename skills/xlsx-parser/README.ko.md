# xlsx-parser (한국어 가이드)

*[English guide → README.md](README.md)*

A1에서 시작하는 깔끔한 표 하나가 *아닌*, **정형화되지 않은 엑셀
스프레드시트**(`.xlsx`/`.xlsm`)를 깔끔한 **Markdown**과 구조화된 **JSON** 요소
트리로 변환하는 Claude 스킬입니다. 한국어+영어를 지원합니다.

## 왜 필요한가

`.xlsx`는 구조화된 XML이라 "그냥 데이터프레임으로 읽으면 되지" 싶지만, 실제
시트는 그 가정을 깨뜨립니다. 한 시트에 제목 행, 단위 표기 행이 있고, 진짜
헤더는 세 줄 아래에 있고, 그 밑에 표가 있고, 빈 줄 하나를 두고 옆이나 아래에
*두 번째* 표가 또 있습니다. 셀은 시각적 묶음을 위해 병합되어 있고, 숫자는
계산된 결과가 필요한 수식이며, 그 위에 차트까지 얹혀 있습니다. 이 모든 걸 한
덩어리로 펼치면 정작 필요했던 구조를 잃게 됩니다.

그래서 이 스킬은 **표 영역을 먼저 감지한 뒤 추출**합니다 — `pdf-parser`와 같은
"분류 먼저(triage-first)" 발상을 스프레드시트에 맞춘 것입니다. 완전히 빈
행/열을 기준으로 각 시트를 잘라 위아래·좌우로 쌓인 표를 따로 뽑아내고, (항상
1행이 아닌) 진짜 헤더 행을 찾고, 병합 셀은 HTML로 그려 정확히 보존하고, 수식은
계산값(없으면 수식 자체)을 드러내고, 차트 데이터는 XML에서 복원하며, 위험한
시트는 검토 대상으로 표시합니다.

## 설치

### Claude Code / Claude Desktop / Cowork

스킬 폴더를 스킬 디렉터리에 넣으면 에이전트가 자동으로 인식합니다. 저장소 루트에서
실행하세요.

```bash
mkdir -p ~/.claude/skills
cp -R skills/xlsx-parser ~/.claude/skills/
```

이미 `skills/xlsx-parser/` 안에 있다면 이렇게 실행합니다.

```bash
mkdir -p ~/.claude/skills/xlsx-parser
cp -R . ~/.claude/skills/xlsx-parser/
```

특정 프로젝트에만 적용하려면 그 프로젝트의 `.claude/skills/` 아래로 복사하면
됩니다. 패키지 파일을 쓰는 앱이라면 저장소 루트에서 빌드한 뒤 **Save skill**
버튼으로 설치할 수 있습니다.

```bash
uv run python scripts/build_all.py xlsx-parser
```

설치 후에는 `.xlsx` 파일을 언급하기만 하면 — “이 엑셀에서 표들 뽑아줘”, “extract
the tables from this messy spreadsheet” — 스킬이 자동으로 동작합니다.
`/xlsx-parser`로 직접 호출할 수도 있습니다.

### Codex, Cursor, 그 밖의 셸 실행 가능한 에이전트

`scripts/`는 평범한 파이썬 CLI입니다(필수 의존성: `openpyxl`. `markitdown`은
`--crosscheck`에서만 쓰는 선택 의존성). `scripts/`를 프로젝트에 복사하고
`pip install openpyxl` 한 뒤, 분류 → 파싱 → 검증 플레이북이 담긴 `SKILL.md`를
에이전트에 알려주면 됩니다.

## 작업 흐름

대부분의 사용자는 먼저 에이전트에게 자연어로 요청하면 됩니다.

- “이 엑셀에서 표들 뽑아줘.”
- “이 워크북 표 구조 그대로 정리해줘.”
- “이 messy 스프레드시트에서 표들을 추출해줘.”
- “이 xlsx를 RAG용 markdown/JSON으로 변환해줘.”

에이전트가 각 시트의 표 영역을 감지해 Markdown + JSON으로 추출하고, 먼저 확인할
저신뢰(low-confidence) 시트를 짚어 줍니다.

명령줄에서 직접 실행할 때는 아래 흐름을 씁니다.

```bash
cd scripts

# 파싱 -> OUTDIR/INPUT.md + INPUT.json
python xlsx_parse.py INPUT.xlsx -o OUTDIR

# 선택: markitdown의 평면 markdown 뷰를 second opinion으로 함께 출력
python xlsx_parse.py INPUT.xlsx -o OUTDIR --crosscheck
```

콘솔에는 시트별로 찾은 표 개수, 신뢰도, 플래그가 출력되고, 마지막에
`🔎 verify these sheets`(확인이 필요한 시트) 목록이 표시됩니다. 전체
흐름(읽기 → 분할 확인 → 플래그된 시트 검증 → 수식값 확인)은 `SKILL.md`를, 영역·
헤더 휴리스틱과 JSON 요소 스키마는 `references/xlsx_internals.md`를 참고하세요.

## 감지하는 항목

| 기능 | 결과물 |
|---|---|
| 표 분할 | 빈 행/열을 기준으로 각 시트를 별도 영역으로 절단. 한 시트에 표가 둘 이상이면 `multiple-table-regions` 플래그 |
| 진짜 헤더 감지 | 1행이 아니어도 라벨 행을 찾는 휴리스틱. 애매한 경우 `header-ambiguous` 플래그 |
| 병합 셀 | `rowspan`/`colspan`을 가진 HTML `<table>`로 렌더링(평면 파이프 표로는 표현 불가). `merged-cells` 플래그 |
| 수식값 | 캐시된 결과가 있으면 읽고(`formula-cells`), 워크북에 캐시가 없으면 **수식 자체**를 표시하며 `formula-no-cache` 플래그 |
| 차트 | 차트 XML에서 카테고리 라벨과 시리즈 값을 **구체적인 배열로 복원**하고, 원본 `series_refs`도 함께 제공 |
| 신뢰도 | 모든 시트에 `confidence` 점수와 `flags` 부여 → 조용한 오류 가능성이 큰 곳에 주의 집중(빈 시트는 `empty-sheet`) |

## 의존성

`openpyxl`이 필수입니다. `markitdown`은 선택이며, `--crosscheck`가 평면
second-opinion 뷰를 출력할 때만 사용합니다.

```bash
pip install openpyxl          # 필수
pip install markitdown        # 선택, --crosscheck 용
```

## 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| 진짜 표 두 개가 하나로 합쳐짐 | 보통 두 표 사이에 완전히 빈 줄이 없어서입니다(엉뚱한 값 하나가 틈을 메움). 그 값을 지우거나 수동으로 분리하세요. |
| 표 하나가 둘로 쪼개짐 | 표 안의 빈 행/열이 빈 줄로 보였습니다 — 그 틈을 채우거나 영역을 수동으로 합치세요. |
| 숫자 대신 `=…`가 보임(`formula-no-cache`) | openpyxl은 수식을 계산하지 않으므로, 비-Excel 도구로 저장된 워크북에는 캐시값이 없습니다. Excel/LibreOffice에서 한 번 열고 저장하면 계산값이 생깁니다. |
| 헤더 행을 잘못 잡음(`header-ambiguous`) | 와이드 피벗이나 3단 이상으로 쌓인 헤더는 감지가 혼란스러울 수 있습니다 — 플래그를 확인하고 헤더 행을 수동으로 고치세요. |
| 제목/메모가 표 행이 아니라 `note`로 나옴 | 의도된 동작입니다 — 표의 헤더를 깔끔하게 유지하기 위함입니다. |
| 저신뢰 시트 | `🔎 verify these sheets` 목록을 먼저 확인하고, `--crosscheck`(markitdown)와 diff해 분할 오류를 빠르게 찾아내세요. |

## 테스트

```bash
python -m pytest tests/xlsx_parser/ -q
```

픽스처는 `tests/xlsx_parser/fixtures/make_fixtures.py`가 처음부터 생성하며
저장소에 커밋하지 않습니다.
