"""Iteration 372 behaviors: an unreadable file under applies_when is UNKNOWN.

A NOT_APPLICABLE decided over a domain in which a file could not be READ
(an OSError such as permission denied) claims "this gap cannot apply here"
about bytes the scanner never saw. The finding must instead be UNKNOWN with a
reason that starts ``applies_when unreadable: `` and names the count.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-10. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Behaviors are
driven through the public in-process ``main()`` entry point with ``capsys``
and by reading the published contract.

Every test that makes a file unreadable skips under root (root reads
anything) and restores ``0o644`` in a ``finally``.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

import pytest

from agent_gap_radar.checks import MAX_FILE_BYTES
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO / "docs" / "CONSUMER_CONTRACT.md"
PRIOR_ANCHOR = "**The search cap and the one verdict it can change.**"
NEW_ANCHOR = "**An unreadable file is weighed under applies_when.**"
PREFIX = "applies_when unreadable: "
# Built at runtime so this module never spells the substring that an
# iteration-252 git-grep guard pins to its one existing site.
OLD_REASON = " ".join(("applies_when", "did", "not", "match"))

F_CONTENT = (
    "import openai\n"
    "client=openai.OpenAI()\n"
    "messages=[]\n"
    'r=client.chat.completions.create(model="m",messages=messages)\n'
    "messages.append(r)\n"
)
EB1_IDS = ("GAP-041", "GAP-043", "GAP-050", "GAP-008")
EB2_IDS = EB1_IDS + ("GAP-003",)

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a chmod 000 file, so unreadable cannot be staged",
)


def run(capsys, argv):
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _git(target: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=target,
        check=True,
        capture_output=True,
    )


def build_target(root: pathlib.Path, files: dict[str, bytes], *, git: bool) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (root / name).write_bytes(data)
    if git:
        _git(root, "init", "-q")
        _git(root, "add", *files)
        _git(root, "commit", "-q", "-m", "fixture")
    return root


def scan_json(capsys, target: pathlib.Path):
    code, out, err = run(capsys, ["scan", target, "--gaps", REPO, "--json"])
    return code, out, err


def by_id(doc: dict) -> dict[str, dict]:
    return {f["gap_id"]: f for f in doc["findings"]}


class Unreadable:
    """Context manager: chmod the named files 000, always restore 0o644."""

    def __init__(self, *paths: pathlib.Path):
        self.paths = paths

    def __enter__(self):
        for p in self.paths:
            p.chmod(0o000)
        return self

    def __exit__(self, *exc):
        for p in self.paths:
            p.chmod(0o644)
        return False


def _assert_unreadable_finding(f: dict, gid: str) -> None:
    assert f["verdict"] == "UNKNOWN", (gid, f["verdict"], f["reason"])
    assert f["verdict"] != "NOT_APPLICABLE"
    assert f["skipped_files"] >= 1, (gid, f["skipped_files"])
    reason = f["reason"]
    assert reason.startswith(PREFIX), (gid, reason)
    m = re.search(r"(\d+) file", reason)
    assert m is not None, (gid, reason)
    assert int(m.group(1)) >= 1, (gid, reason)


# EB1 -----------------------------------------------------------------------


def test_eb1_readable_baseline_unchanged(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    code, out, err = scan_json(capsys, target)
    assert code == 0, err
    doc = json.loads(out)
    found = by_id(doc)
    for gid in EB1_IDS:
        assert found[gid]["verdict"] == "PRESENT", (gid, found[gid])
    assert [f["gap_id"] for f in doc["findings"] if f["verdict"] == "UNKNOWN"] == []
    assert doc["counts"]["UNKNOWN"] == 0
    assert all(f["skipped_files"] == 0 for f in doc["findings"])
    assert not any(f["reason"].startswith(PREFIX) for f in doc["findings"])


# EB2 / EB3 / EB4 -----------------------------------------------------------


@needs_non_root
def test_eb2_unreadable_git_variant_is_unknown(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with Unreadable(target / "a.py"):
        code, out, err = scan_json(capsys, target)
    assert code == 0
    assert err == ""
    found = by_id(json.loads(out))
    for gid in EB2_IDS:
        _assert_unreadable_finding(found[gid], gid)
    # Exactly one file is unreadable: the count named is 1.
    assert re.search(r"\b1 file", found["GAP-041"]["reason"]), found["GAP-041"]["reason"]


@needs_non_root
def test_eb3_new_reason_never_reuses_the_guarded_substring(tmp_path, capsys):
    assert OLD_REASON.count(" ") == 3
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with Unreadable(target / "a.py"):
        code, out, _ = scan_json(capsys, target)
    assert code == 0
    new = [f for f in json.loads(out)["findings"] if f["reason"].startswith(PREFIX)]
    assert new, "the new branch produced no reason at all"
    assert [f["gap_id"] for f in new if OLD_REASON in f["reason"]] == []


@needs_non_root
def test_eb4_cause_survives_the_read_cache(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with Unreadable(target / "a.py"):
        code, out, _ = scan_json(capsys, target)
    assert code == 0
    doc = json.loads(out)
    counts = doc["counts"]
    assert counts["UNKNOWN"] >= 90, counts
    assert counts["NOT_APPLICABLE"] <= 20, counts
    flipped = [f for f in doc["findings"] if f["reason"].startswith(PREFIX)]
    assert len(flipped) >= 90, len(flipped)
    # Counts agree with the findings they summarise.
    tally = {}
    for f in doc["findings"]:
        tally[f["verdict"]] = tally.get(f["verdict"], 0) + 1
    for verdict, n in counts.items():
        assert tally.get(verdict, 0) == n, (verdict, tally, counts)


# EB5 -----------------------------------------------------------------------


@needs_non_root
def test_eb5_walk_variant_parity(tmp_path, capsys):
    git_t = build_target(tmp_path / "Fg", {"a.py": F_CONTENT.encode()}, git=True)
    walk_t = build_target(tmp_path / "Fw", {"a.py": F_CONTENT.encode()}, git=False)
    assert not (walk_t / ".git").exists()
    with Unreadable(git_t / "a.py", walk_t / "a.py"):
        cg, og, eg = scan_json(capsys, git_t)
        cw, ow, ew = scan_json(capsys, walk_t)
    assert (cg, cw) == (0, 0), (eg, ew)
    fg, fw = by_id(json.loads(og)), by_id(json.loads(ow))
    for gid in EB2_IDS:
        _assert_unreadable_finding(fw[gid], gid)
        assert fw[gid]["verdict"] == fg[gid]["verdict"] == "UNKNOWN", gid


# EB6 -----------------------------------------------------------------------


@needs_non_root
def test_eb6_markdown_surface(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with Unreadable(target / "a.py"):
        code, out, err = run(capsys, ["scan", target, "--gaps", REPO])
    assert code == 0, err
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert PREFIX in out
    lines = out.splitlines()
    hits = [i for i, line in enumerate(lines) if "GAP-041" in line]
    assert hits, "GAP-041 not in the markdown report"
    # UNKNOWN appears on GAP-041's row, or in the heading of its section.
    for i in hits:
        heading = next((lines[j] for j in range(i, -1, -1) if lines[j].startswith("#")), "")
        assert "UNKNOWN" in lines[i] or "UNKNOWN" in heading, (lines[i], heading)
        assert "PRESENT" not in heading and "NOT_APPLICABLE" not in heading, heading
    assert any(PREFIX in lines[i] for i in hits), [lines[i] for i in hits]


# EB7 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,data",
    [
        ("big.py", b"x = 1\n" * (MAX_FILE_BYTES // 6 + 10)),
        ("bad.py", b"\xff\xfe\x00bad"),
    ],
    ids=["oversized", "non-utf8"],
)
def test_eb7_other_skip_causes_make_no_new_unknown(tmp_path, capsys, name, data):
    if name == "big.py":
        assert len(data) > MAX_FILE_BYTES
    target = build_target(tmp_path / "G", {name: data}, git=True)
    code, out, err = scan_json(capsys, target)
    assert code == 0, err
    doc = json.loads(out)
    assert [f["gap_id"] for f in doc["findings"] if f["reason"].startswith(PREFIX)] == []
    assert doc["counts"]["NOT_APPLICABLE"] > 0, doc["counts"]
    assert doc["counts"]["NOT_APPLICABLE"] >= 90, doc["counts"]


# EB8 -----------------------------------------------------------------------


@needs_non_root
def test_eb8_a_match_still_wins(tmp_path, capsys):
    target = build_target(
        tmp_path / "F",
        {"a.py": F_CONTENT.encode(), "b.py": b"print('hello')\n"},
        git=True,
    )
    with Unreadable(target / "b.py"):
        code, out, err = scan_json(capsys, target)
    assert code == 0, err
    found = by_id(json.loads(out))
    assert found["GAP-041"]["verdict"] == "PRESENT", found["GAP-041"]
    for gid in EB1_IDS:
        assert found[gid]["verdict"] == "PRESENT", (gid, found[gid])


# EB9 -----------------------------------------------------------------------


@needs_non_root
def test_eb9_unreadable_scan_is_deterministic(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with Unreadable(target / "a.py"):
        c1, o1, _ = scan_json(capsys, target)
        c2, o2, _ = scan_json(capsys, target)
    assert (c1, c2) == (0, 0)
    assert o1 == o2
    assert o1.endswith("}\n") and not o1.endswith("\n\n")


@needs_non_root
def test_eb9_chmod_is_restored(tmp_path, capsys):
    target = build_target(tmp_path / "F", {"a.py": F_CONTENT.encode()}, git=True)
    with pytest.raises(RuntimeError):
        with Unreadable(target / "a.py"):
            raise RuntimeError("boom")
    assert (target / "a.py").read_text() == F_CONTENT
    code, out, _ = scan_json(capsys, target)
    assert code == 0
    assert json.loads(out)["counts"]["UNKNOWN"] == 0


# EB10 ----------------------------------------------------------------------


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def test_eb10_contract_paragraph_follows_the_search_cap_paragraph():
    paras = _paragraphs(CONTRACT_DOC.read_text(encoding="utf-8"))
    prior = [i for i, p in enumerate(paras) if p.lstrip().startswith(PRIOR_ANCHOR)]
    new = [i for i, p in enumerate(paras) if p.lstrip().startswith(NEW_ANCHOR)]
    assert len(prior) == 1, prior
    assert len(new) == 1, new
    assert new[0] == prior[0] + 1, (prior, new)


def _new_paragraph() -> str:
    paras = _paragraphs(CONTRACT_DOC.read_text(encoding="utf-8"))
    (para,) = [p for p in paras if p.lstrip().startswith(NEW_ANCHOR)]
    return " ".join(para.split())


def test_eb10_contract_paragraph_content():
    para = _new_paragraph()
    low = para.lower()
    # Ambiguity noted: the spec mandates the literal non-UTF-8 AND "no digit";
    # the encoding name is the one digit-bearing token allowed.
    assert not re.search(r"\d", para.replace("UTF-8", "UTF")), re.findall(r"\d+", para)
    assert "NOT_APPLICABLE" in para
    assert "UNKNOWN" in para
    assert "`skipped_files`" in para or "skipped_files" in para
    assert "un-answered" in low
    assert "gate" in low
    assert "oversized" in low
    assert "non-utf-8" in low or "not decodable" in low
    assert "could not be read" in low or "unreadable" in low


def test_eb10_new_paragraph_separated_by_blank_line():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    idx = text.index(NEW_ANCHOR)
    assert text[idx - 2 : idx] == "\n\n", repr(text[idx - 4 : idx])
    assert text.count(NEW_ANCHOR) == 1
