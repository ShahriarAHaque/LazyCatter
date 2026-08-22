#!/usr/bin/env python3
"""offline checks for roles/mover pure helpers
no discord"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bot"))

from mover import JobLog, build_body, name_matches, new_embed_urls, split_content  # noqa: E402


def test_split():
    assert split_content("") == []
    assert split_content("hi") == ["hi"]
    long = ("line\n" * 500)
    parts = split_content(long, 2000)
    assert all(len(p) <= 2000 for p in parts)


def test_joblog():
    j = JobLog()
    assert not j.done(1)
    j.mark(1, [9, 10])
    assert j.done(1)
    j2 = JobLog.from_json(j.to_json())
    assert j2.moved["1"] == ["9", "10"]


def test_library_helpers():
    assert name_matches("Library of Example", ["library of example"])
    assert new_embed_urls(["https://a/img.png"], "hi") == ["https://a/img.png"]
    assert new_embed_urls(["https://a/img.png"], "see https://a/img.png") == []
    body = build_body("caption", "https://discord.com/channels/1/2/3", True, ["https://cdn/x.png"])
    assert any("caption" in p for p in body)
    assert any("cdn/x" in p for p in body)
    assert any("from:" in p for p in body)


if __name__ == "__main__":
    test_split()
    test_joblog()
    test_library_helpers()
    print("ok")
