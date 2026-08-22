"""app version
read from VERSION at repo root
bundled for frozen builds"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["VERSION", "PUBLISHER", "COPYRIGHT", "DEVELOPER_GITHUB"]

PUBLISHER = "LilaNaCl"
COPYRIGHT = "LilaNaCl (Shahriar Haque)"
DEVELOPER_GITHUB = "ShahriarAHaque"


def _read_version() -> str:
    candidates = []
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "VERSION")
    if getattr(__import__("sys"), "frozen", False):
        import sys

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "VERSION")
        candidates.append(Path(sys.executable).resolve().parent / "VERSION")
    env = os.environ.get("LAZYCATTER_VERSION", "").strip()
    if env:
        return env
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
        except OSError:
            continue
    return "0.1.0"


VERSION = _read_version()
