#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Example: fill a Korean .hwp form (hwp-toolkit) and verify formatting is kept.

    python examples/hwp_fill_form.py
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "skills", "hwp-toolkit", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests", "hwp_toolkit", "fixtures"))

import hwp_lib            # noqa: E402
import make_fixtures      # noqa: E402

src = make_fixtures.form()
out = os.path.join(os.path.dirname(src), "_filled_example.hwp")

# 1) unambiguous field -> find/replace
hwp_lib.replace_text(src, out, [(" ㅇ 비고 : ", " ㅇ 비고 : 작성 완료")])

# 2) three identical '담당자: [[NAME]]' -> set only the 2nd by record index
info = hwp_lib.inspect(out)
idxs = [x["rec_index"] for x in info["sections"][0]["paragraphs"]
        if x["text"].startswith("담당자")]
hwp_lib.set_paragraph_text(out, out, {"BodyText/Section0": {idxs[1]: "담당자: 홍길동"}})

print(hwp_lib.extract_text(out))
print("\nSaved:", out)
