# pptx-parser (한국어 가이드)

*[English guide → README.md](README.md)*

**파워포인트 덱**(`.pptx`)을 올바른 읽기 순서로 깔끔한 **Markdown**과 구조화된
**JSON** 요소 트리로 변환하는 Claude 스킬입니다. 제목, 글머리 기호 텍스트, 표
(병합 셀 포함), 차트(범주와 계열 값을 XML에서 정확히 복원), 그림, 그룹 도형,
발표자 노트까지 뽑아냅니다. 한국어+영어를 지원합니다.

## 왜 필요한가

슬라이드는 자유로운 캔버스라 도형이 아무 데나 배치됩니다. 그래서 python-pptx가
돌려주는 순서(z-order)는 사람이 읽는 순서가 **아닙니다**. 단순 텍스트 덤프는
슬라이드를 뒤섞고, 가장 중요한 것들 — 표, 차트(데이터가 XML 안에 들어 있어
*정확히* 읽을 수 있는데도), 그룹 도형, 발표자 노트 — 을 떨어뜨립니다. 이
스킬은 대신 슬라이드마다 도형을 **기하학적 위치로 정렬**(위→아래, 왼→오른쪽 —
슬라이드 버전의 읽기 순서)하고, 그룹 도형 안으로 재귀해 들어가며, 표·차트·
그림·노트를 다른 파서와 동일한 구조화된 요소 트리로 추출하고, 사람이 확인해야
할 슬라이드에는 플래그를 답니다.

## 설치

### Claude Code / Claude Desktop / Cowork

스킬 폴더를 스킬 디렉터리에 넣으면 에이전트가 자동으로 인식합니다. 저장소 루트에서
실행하세요.

```bash
mkdir -p ~/.claude/skills
cp -R skills/pptx-parser ~/.claude/skills/
```

이미 `skills/pptx-parser/` 안에 있다면 이렇게 실행합니다.

```bash
mkdir -p ~/.claude/skills/pptx-parser
cp -R . ~/.claude/skills/pptx-parser/
```

특정 프로젝트에만 적용하려면 그 프로젝트의 `.claude/skills/` 아래로 복사하면
됩니다. 패키지 파일을 쓰는 앱이라면 저장소 루트에서 `dist/pptx-parser.skill`을
빌드한 뒤 **Save skill** 버튼으로 설치할 수 있습니다.

```bash
uv run python scripts/build_all.py pptx-parser
```

설치 후에는 `.pptx` 파일을 언급하기만 하면 — “이 PPT에서 텍스트랑 표, 차트
데이터까지 뽑아줘”, “convert this deck.pptx to markdown with the chart
numbers” — 스킬이 자동으로 동작합니다. `/pptx-parser`로 직접 호출할 수도
있습니다.

### Codex, Cursor, 그 밖의 셸 실행 가능한 에이전트

`scripts/`는 평범한 파이썬 CLI입니다(의존성: `python-pptx`; `markitdown`은
선택적 교차 확인용). `scripts/`를 프로젝트에 복사하고
`pip install python-pptx` 한 뒤, 파싱 → 플래그 슬라이드 확인 → 비전 전사 →
검증 플레이북이 담긴 `SKILL.md`를 에이전트에 알려주면 됩니다.

## 작업 흐름

대부분의 사용자는 먼저 에이전트에게 자연어로 요청하면 됩니다.

- “이 PPT에서 텍스트랑 표, 차트 데이터까지 뽑아줘.”
- “이 deck.pptx를 차트 수치까지 포함해 Markdown으로 바꿔줘.”
- “모든 슬라이드의 내용과 발표자 노트를 JSON으로 뽑아줘.”
- “이 프레젠테이션에서 표만 뽑아줘.” / “이 슬라이드 내용 정리해줘.”

에이전트가 슬라이드마다 도형을 기하학적 순서로 정렬하고, 표·차트·노트를 읽고,
이미지 전용이나 겹치는 슬라이드에는 플래그를 달며, 필요한 슬라이드만 비전으로
전사합니다.

명령줄에서 직접 실행할 때는 아래 흐름을 씁니다.

```bash
cd scripts

# 파싱 -> OUTDIR/INPUT.md + INPUT.json
python pptx_parse.py INPUT.pptx -o OUTDIR

# markitdown을 두 번째 의견으로 추가 -> OUTDIR/INPUT.markitdown.md
python pptx_parse.py INPUT.pptx -o OUTDIR --crosscheck
```

전체 흐름은 `SKILL.md`를, 기하학적 정렬·차트/표 추출·신뢰도 모델·JSON 요소
스키마는 `references/pptx_internals.md`를 참고하세요.

## 슬라이드 플래그

각 슬라이드는 신뢰도 점수와 `flags` 목록을 가지며, 신뢰도가 낮은 슬라이드는
Markdown에 인라인 `🔎` 메모도 함께 붙습니다.

| 플래그 | 의미 | 해야 할 일 |
|------|---------|------------|
| `image-only-slide` | 추출 가능한 텍스트 없음 — 메시지가 그림 안에 있음 | 별도로 렌더링해 비전으로 전사하세요 |
| `needs-vision` | 시각적 확인이 필요한 슬라이드(예: 이미지 전용) | `vision_slides`에 나열됨; 비전으로 전사 |
| `overlapping-shapes-order-ambiguous` | 도형이 겹쳐 기하학적 순서가 틀릴 수 있음 | 원본과 그 슬라이드의 순서를 눈으로 확인하세요 |
| `grouped-shapes` | 그룹이 읽기 순서로 평탄화됨 | 계층이 의미를 담고 있다면 확인하세요 |
| `table-merged-cells` | 표에 병합 셀이 있음(`<table>` HTML로 출력) | 병합 범위가 제대로 읽혔는지 확인하세요 |
| `has-chart` | 차트 데이터를 XML에서 복원함 | 각 계열이 기대한 레이블을 받았는지 확인하세요 |
| `empty-slide` | 추출할 내용이 없는 슬라이드 | 추출할 것이 없음 |

## 의존성

`python-pptx`가 필수입니다. `markitdown`은 선택 사항이며 `--crosscheck`에만
쓰입니다.

```bash
pip install python-pptx
# 선택, --crosscheck 용:
pip install markitdown
```

## 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| 슬라이드에 텍스트가 하나도 안 나옴 | `image-only-slide`(스크린샷·다이어그램)입니다 — 내용이 그림 안에 있으니 비전으로 전사하세요. 그림은 표시만 하고 추출하지 않습니다. |
| 도형 순서가 뒤섞임 | 그 슬라이드에 `overlapping-shapes-order-ambiguous`가 붙은 경우입니다 — 도형이 겹치면 기하학적 순서가 틀릴 수 있으니 원본과 대조해 확인하세요. |
| 차트 값이 이상해 보임 | 범주와 계열은 XML에서 그대로 읽어 정확합니다 — 다만 각 계열이 기대한 레이블을 받았는지 확인하세요(`has-chart`). |
| 차트 종류가 `COLUMN_CLUSTERED (51)`로 나옴 | 차트에 제목이 없어 enum 종류가 표시된 것입니다 — 오류가 아니라 차트 유형입니다. |
| 그림이 추출되지 않음 | 의도된 동작입니다 — 그림은 Markdown에 주석으로 표시만 하고 이미지 파일로 추출하지 않습니다. |
| `ModuleNotFoundError: pptx` | `pip install python-pptx` 하고, 스크립트는 `scripts/` 디렉터리에서 실행하세요. |

## 테스트

```bash
python -m pytest tests/pptx_parser/ -q
```

픽스처는 `tests/pptx_parser/fixtures/make_fixtures.py`가 처음부터 생성하며
저장소에 커밋하지 않습니다.
