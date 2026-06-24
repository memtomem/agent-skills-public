# memtomem-skills

*[English → README.md](README.md)*

[Claude](https://claude.com)와 여러 코딩 에이전트에서 사용할 수 있는
설치형 **스킬(skill) 모음**입니다. 각 스킬은 한 가지 일을 안정적으로 처리하기 위한
지침, 실행 스크립트, 참고 문서를 함께 제공합니다.

일반 도구로는 깨지는 문서에서 깔끔하고 구조화된 내용을 뽑아내는 데 초점을
둡니다 — 아래아한글 / 한컴오피스 문서와 정형화되지 않은 PDF를 다룹니다.

## 스킬 목록

| 스킬 | 하는 일 | 상태 |
|---|---|---|
| [`hwp-toolkit`](skills/hwp-toolkit/) | 아래아한글 / 한컴오피스 문서(`.hwp` / `.hwpx`)를 읽고, 구조를 확인하고, 양식을 채웁니다. 텍스트 추출, 문서 구조 검사, 자리표시자 치환, 한글 서식 채우기를 지원하며 기존 레이아웃을 보존합니다. | 안정 버전 |
| [`pdf-parser`](skills/pdf-parser/) | 정형화되지 않은 복잡한 PDF(혼합 본문, 다단, 괘선 표, 차트, 스캔 페이지)를 깔끔한 Markdown + 구조화된 JSON 요소 트리로 변환합니다. 페이지별로 분류해 스캔·도형 페이지는 비전(vision)으로 보냅니다. 한국어+영어 지원. | 안정 버전 |

스킬은 [`skills/`](skills/) 아래에 계속 추가됩니다.

## 시작하기

### Claude Code / Claude Desktop / Cowork

스킬 폴더를 스킬 디렉터리에 넣으면 에이전트가 자동으로 인식합니다(권장):

```bash
cp -R skills/hwp-toolkit ~/.claude/skills/    # 또는: cp -R skills/pdf-parser ...
```

앱이 스킬 가져오기를 지원한다면 `.skill` 패키지를 사용해도 됩니다:

```bash
uv run python scripts/build_all.py            # 모든 dist/<name>.skill 빌드
```

그다음 원하는 `dist/<name>.skill`을 앱의 **Save skill** 또는 스킬 가져오기
기능으로 설치합니다.

설치 후에는 프롬프트에서 파일이나 작업을 언급하면 됩니다 — `.hwp` / `.hwpx`
문서, 추출할 PDF, "한글 문서" 등. 에이전트가 알맞은 스킬을 읽고 필요한 단계를
대신 수행합니다.

### Codex, Cursor, 그 밖의 코딩 에이전트

각 스킬에는 일반 파이썬 명령줄 도구가 `scripts/` 폴더에 들어 있습니다.
`.skill` 패키지를 직접 지원하지 않는 에이전트에서는 스킬 폴더나 스크립트를
프로젝트에 복사한 뒤, 그 스킬의 `SKILL.md` 플레이북을 참고하도록 알려주면 됩니다.

- **hwp-toolkit** — [`SKILL.md`](skills/hwp-toolkit/SKILL.md) · [`README.md`](skills/hwp-toolkit/README.md)
- **pdf-parser** — [`SKILL.md`](skills/pdf-parser/SKILL.md) · [`README.md`](skills/pdf-parser/README.md)

## 요청 예시

자연어로 요청하면 에이전트가 알맞은 스킬을 고릅니다.

**hwp-toolkit**

- "`application.hwp`에서 표를 포함해 텍스트를 추출해줘."
- "이 한글 `.hwp` 양식에서 강좌명과 강사명을 채워줘."
- "이 `.hwpx` 문서를 깔끔한 Markdown으로 변환해줘."

**pdf-parser**

- "이 `report.pdf`를 표는 표로 유지하면서 Markdown으로 변환해줘."
- "이 PDF에서 표랑 본문만 마크다운으로 뽑아줘."
- "이 스캔된 계약서 PDF를 분류하고 스캔 페이지를 전사(transcribe)해줘."
- "이 PDF의 표를 pandas로 불러올 수 있게 JSON으로 뽑아줘."

## 바로가기

**hwp-toolkit**

- 사용 가이드: [`README.ko.md`](skills/hwp-toolkit/README.ko.md) · [문제 해결](skills/hwp-toolkit/README.ko.md#문제-해결) · [.hwp와 .hwpx 차이](skills/hwp-toolkit/README.ko.md#두-포맷의-차이)
- 영문 가이드: [`README.md`](skills/hwp-toolkit/README.md) · 작업 지침: [`SKILL.md`](skills/hwp-toolkit/SKILL.md)

**pdf-parser**

- 사용 가이드: [`README.ko.md`](skills/pdf-parser/README.ko.md) · 영문 가이드: [`README.md`](skills/pdf-parser/README.md)
- 작업 지침: [`SKILL.md`](skills/pdf-parser/SKILL.md) · 포맷 내부 구조: [`references/pdf_internals.md`](skills/pdf-parser/references/pdf_internals.md)

이 저장소에는 비공개 문서나 제3자 문서를 포함하지 않습니다.

## 라이선스

[MIT](LICENSE) © 2026 memtomem
