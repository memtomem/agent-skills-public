# memtomem-skills

*[한국어 → README.ko.md](README.ko.md)*

Installable **skills** for [Claude](https://claude.com) and other coding agents.
Each skill packages a focused instruction manual with the scripts and references
needed to complete one specialized task reliably.

The collection focuses on getting clean, structured content out of documents that
ordinary tools mishandle — Korean Hangul Word Processor files and messy,
unstructured PDFs.

## Skills

| Skill | What it does | Status |
|---|---|---|
| [`hwp-toolkit`](skills/hwp-toolkit/) | Read, inspect, and fill Hangul Word Processor files (`.hwp` / `.hwpx`, 아래아한글 / 한컴오피스). Extract text, inspect document structure, replace placeholders, and fill Korean form templates while preserving layout. | Stable |
| [`pdf-parser`](skills/pdf-parser/) | Parse messy, unstructured PDFs (mixed text, multi-column, ruled tables, charts, scanned pages) into clean Markdown + a structured JSON element tree. Triages each page and routes scanned/figure pages to vision. Korean + English. | Stable |

More skills will be added under [`skills/`](skills/) over time.

## Get Started

### Claude Code / Claude Desktop / Cowork

Drop a skill folder into your skills directory and the agent picks it up
automatically (recommended):

```bash
cp -R skills/hwp-toolkit ~/.claude/skills/    # or: cp -R skills/pdf-parser ...
```

You can also import the packaged `.skill` file when your app offers skill import:

```bash
uv run python scripts/build_all.py            # builds every dist/<name>.skill
```

Then import the `dist/<name>.skill` you want with the app's **Save skill** or
skill import flow.

After installation, just mention the file or task in your prompt — a `.hwp` /
`.hwpx` document, a PDF to extract, "한글 문서", etc. The agent reads the matching
skill and runs the right steps for you.

### Codex, Cursor, or Other Coding Agents

Each skill ships normal Python command-line tools under its `scripts/` folder.
For agents that don't support `.skill` packages directly, copy the skill folder
or scripts into your project and point your agent at its `SKILL.md` playbook:

- **hwp-toolkit** — [`SKILL.md`](skills/hwp-toolkit/SKILL.md) · [`README.md`](skills/hwp-toolkit/README.md)
- **pdf-parser** — [`SKILL.md`](skills/pdf-parser/SKILL.md) · [`README.md`](skills/pdf-parser/README.md)

## Example Prompts

Ask in plain language; the agent picks the skill.

**hwp-toolkit**

- "Extract the text from this `application.hwp`, including tables."
- "Fill the course title and instructor name in this Korean `.hwp` form template."
- "Convert this `.hwpx` document into clean Markdown."

**pdf-parser**

- "Convert this `report.pdf` to Markdown and keep the tables as tables."
- "이 PDF에서 표랑 본문만 마크다운으로 뽑아줘."
- "Triage this scanned contract PDF and transcribe the scanned pages."
- "Pull the tables out of this PDF into JSON I can load into pandas."

## Useful Links

**hwp-toolkit**

- User guide: [`README.md`](skills/hwp-toolkit/README.md) · [Troubleshooting](skills/hwp-toolkit/README.md#troubleshooting) · [.hwp vs .hwpx](skills/hwp-toolkit/README.md#how-the-two-formats-differ)
- Korean guide: [`README.ko.md`](skills/hwp-toolkit/README.ko.md) · Agent playbook: [`SKILL.md`](skills/hwp-toolkit/SKILL.md)

**pdf-parser**

- User guide: [`README.md`](skills/pdf-parser/README.md) · Korean guide: [`README.ko.md`](skills/pdf-parser/README.ko.md)
- Agent playbook: [`SKILL.md`](skills/pdf-parser/SKILL.md) · Format internals: [`references/pdf_internals.md`](skills/pdf-parser/references/pdf_internals.md)

No private or third-party documents are included in this repository.

## License

[MIT](LICENSE) © 2026 memtomem
