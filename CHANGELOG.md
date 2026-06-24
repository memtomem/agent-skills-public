# Changelog

All notable changes to this collection are documented here.

## [Unreleased]

### Added
- Initial `memtomem-skills` collection monorepo.
- **hwp-toolkit 0.2.0** — read / analyze / edit Hangul Word Processor files:
  - Binary `.hwp` 5.x text extraction (inline-control aware), structure &
    metadata inspection, find-replace and index-based cell editing with a full
    OLE2 compound-file rewriter that preserves untouched streams byte-for-byte.
  - `.hwpx` (OWPML zip) reading support; multi-section documents extracted with
    `=== section ===` headers.
  - `.hwpx` editing via `hwp_edit.py replace` / `replace_text()`: rewrites only
    the edited `Contents/section*.xml` and copies every other zip member
    through verbatim (STORED `mimetype` stays first), preserving inline elements
    (`<hp:lineBreak/>`, `<hp:tab/>`, markup) in edited runs.
  - `.hwpx` extraction now resolves `<hp:lineBreak/>`→newline and `<hp:tab/>`→
    tab and strips other inline markup, instead of leaking raw XML tags.
  - pytest suite with from-scratch fixtures; `scripts/build_all.py` packaging.
