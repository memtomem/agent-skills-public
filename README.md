# memtomem-skills

*[한국어 → README.ko.md](README.ko.md)*

Installable **document-processing skills** for [Claude](https://claude.com) and
other coding agents. Each skill bundles:

- a `SKILL.md` playbook that tells an agent exactly what to do,
- runnable Python scripts for direct command-line use,
- references and tests that keep the behavior reproducible.

The collection focuses on getting clean, structured content out of documents that
ordinary tools mishandle — Korean Hangul Word Processor files and messy,
unstructured PDFs.

## Which skill do I need?

| I have... | Use | Output |
|---|---|---|
| a Korean Hangul document (`.hwp` / `.hwpx`) | [`hwp-toolkit`](skills/hwp-toolkit/) | extracted text, structure inspection, or a filled copy of the original form |
| a real-world PDF with tables, columns, scans, or charts | [`pdf-parser`](skills/pdf-parser/) | clean Markdown, JSON elements, rendered page assets, and vision placeholders where needed |

More skills will be added under [`skills/`](skills/) over time.

## Fastest path

### 1. Install a skill for Claude Code / Claude Desktop / Cowork

From the repository root:

```bash
mkdir -p ~/.claude/skills
cp -R skills/hwp-toolkit ~/.claude/skills/    # for .hwp / .hwpx
cp -R skills/pdf-parser ~/.claude/skills/     # for PDFs
```

If your app imports packaged skills, build the `.skill` files instead:

```bash
uv run python scripts/build_all.py            # builds every dist/<name>.skill
```

Then import the `dist/<name>.skill` file you want with the app's **Save skill**
or skill import flow.

### 2. Ask in plain language

After installation, mention the file and the result you want:

- "`application.hwp`에서 표를 포함해 텍스트를 추출해줘."
- "Fill the course title and instructor name in this Korean `.hwp` template."
- "Convert `report.pdf` to Markdown and keep tables as tables."
- "Triage this scanned contract PDF and transcribe the scanned pages."

The agent reads the matching skill, runs the scripts, and returns the extracted
content or a new edited file. The original document should not be overwritten.

### 3. Use with Codex, Cursor, or another shell-capable agent

Each skill ships normal Python command-line tools under its `scripts/` folder.
For agents that do not support `.skill` packages directly, copy the skill folder
or scripts into your project and point the agent at its `SKILL.md` playbook:

- **hwp-toolkit** — [`SKILL.md`](skills/hwp-toolkit/SKILL.md) · [`README.md`](skills/hwp-toolkit/README.md)
- **pdf-parser** — [`SKILL.md`](skills/pdf-parser/SKILL.md) · [`README.md`](skills/pdf-parser/README.md)

## Direct CLI examples

Use these when you want to run the scripts yourself rather than through an
agent.

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
```

Install all development dependencies first if you are using the scripts from a
fresh checkout:

```bash
uv venv
uv pip install -r requirements-dev.txt
```

## For contributors

```bash
uv run pytest -q
uv run python scripts/build_all.py
```

Fixtures are generated from scratch by the test suite. Do not commit private
documents, customer files, or generated binary fixtures.

## Guides

**hwp-toolkit**

- User guide: [`README.md`](skills/hwp-toolkit/README.md) · [Troubleshooting](skills/hwp-toolkit/README.md#troubleshooting) · [.hwp vs .hwpx](skills/hwp-toolkit/README.md#how-the-two-formats-differ)
- Korean guide: [`README.ko.md`](skills/hwp-toolkit/README.ko.md) · Agent playbook: [`SKILL.md`](skills/hwp-toolkit/SKILL.md)

**pdf-parser**

- User guide: [`README.md`](skills/pdf-parser/README.md) · Korean guide: [`README.ko.md`](skills/pdf-parser/README.ko.md)
- Agent playbook: [`SKILL.md`](skills/pdf-parser/SKILL.md) · Format internals: [`references/pdf_internals.md`](skills/pdf-parser/references/pdf_internals.md)

## License

[MIT](LICENSE) © 2026 memtomem
