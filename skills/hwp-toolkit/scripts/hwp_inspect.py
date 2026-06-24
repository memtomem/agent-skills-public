#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect the structure of an .hwp file.

Usage:
  python hwp_inspect.py INPUT.hwp [--json] [--paragraphs]

Default: prints streams, compression/encryption flags, per-section record
tag counts. With --paragraphs it also lists every PARA_TEXT with its record
index — this index is what you pass to the editor (hwp_edit.py set) to fill
specific cells precisely. With --json it dumps the full inspection dict.
"""
import argparse
import json
import hwp_lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--paragraphs", action="store_true")
    args = ap.parse_args()
    info = hwp_lib.inspect(args.input)

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    print(f"path        : {info['path']}")
    print(f"compressed  : {info['compressed']}")
    print(f"encrypted   : {info['encrypted']}")
    print("streams     :")
    for n, sz in info["streams"].items():
        print(f"  {sz:>8}  {n!r}")
    if info["encrypted"]:
        print("\n[!] Encrypted/password-protected — body text unavailable.")
        return
    for sec in info["sections"]:
        print(f"\n== {sec['name']}  ({sec['record_count']} records) ==")
        tc = ", ".join(f"{k}:{v}" for k, v in sorted(sec["tag_counts"].items()))
        print("  tags:", tc)
        if args.paragraphs:
            print("  paragraphs (rec_index | level | text):")
            for p in sec["paragraphs"]:
                print(f"   {p['rec_index']:>4} | L{p['level']} | {p['text']!r}")
            if sec.get("blank_paragraphs"):
                print("  blank paragraphs (header_index | suggested level):")
                for p in sec["blank_paragraphs"]:
                    print(f"   {p['header_index']:>4} | "
                          f"L{p['suggested_text_level']}")


if __name__ == "__main__":
    main()
