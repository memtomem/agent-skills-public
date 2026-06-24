#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Package every skill under skills/<name>/ into dist/<name>.skill.

A .skill is a zip whose root contains SKILL.md. Run from anywhere:
    python scripts/build_all.py            # build all skills
    python scripts/build_all.py hwp-toolkit  # build one
"""
import os
import sys
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILLS = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")


def build_one(name):
    sdir = os.path.join(SKILLS, name)
    if not os.path.exists(os.path.join(sdir, "SKILL.md")):
        raise SystemExit(f"skills/{name}/SKILL.md not found")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{name}.skill")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dns, fns in os.walk(sdir):
            # Skip caches and dev-only dirs (evals/ holds QA prompts, not runtime).
            dns[:] = [d for d in dns if d not in ("__pycache__", "evals")]
            for fn in fns:
                if fn.endswith(".pyc"):
                    continue
                full = os.path.join(dp, fn)
                z.write(full, os.path.relpath(full, sdir))  # SKILL.md at root
    with zipfile.ZipFile(out) as z:
        assert "SKILL.md" in z.namelist(), "SKILL.md must be at archive root"
    print(f"Built dist/{name}.skill ({os.path.getsize(out)} bytes)")
    return out


def discover():
    if not os.path.isdir(SKILLS):
        return []
    return sorted(d for d in os.listdir(SKILLS)
                  if os.path.exists(os.path.join(SKILLS, d, "SKILL.md")))


def main(argv):
    names = argv[1:] or discover()
    if not names:
        raise SystemExit("No skills found under skills/")
    for n in names:
        build_one(n)


if __name__ == "__main__":
    main(sys.argv)
