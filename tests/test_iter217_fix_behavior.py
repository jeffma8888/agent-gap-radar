"""Iteration 217, fix pass -- the SHAPE probe at `cli._resolve` must refuse, not guess.

The iteration's own guard lives at `registry.load_all`'s enumeration and is covered by
the spec's behaviour module. This file pins the ONE case that guard cannot see, which
the reviewer found and which is the same defect class one door earlier: a register root
that is READABLE but not SEARCHABLE (mode `0o444`).

There, `iterdir(<root>)` succeeds on the `r` bit and yields only `gaps`, so `load_all`
legitimately sees zero `*.json` records and cannot know a register was hidden from it;
the only site that knows is `_resolve`'s `<root>/gaps` probe, whose `stat` needs the `x`
bit and therefore raises `EACCES`. Answering that unanswerable probe with "no nested
`gaps/`" published four false zero-record answers at exit 0 (`list` 1 B, `list --json`
118 B of all-zero census, `report` 789 B) and blamed emptiness / the evidence / the id
in the other three -- exactly the outcome roadmap row 120 was written against.

Offline, deterministic, `tmp_path` only: the live `gaps/` is never read or written.
Permission fixtures probe-and-skip when the mode does not block (root, or a filesystem
that ignores it) and restore a readable mode in teardown so the temp tree can be removed.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import registry
from agent_gap_radar.cli import _resolve, main

#: Minimal record that satisfies the shipped schema; two copies make the register
#: non-empty, so a zero-record answer can only come from the hidden directory.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}

#: The three sentences the refusal may never substitute itself for: each attributes the
#: failure to the register's contents rather than to the directory that could not be read.
FALSE_ATTRIBUTIONS = ("no gap records found", "no gap clears the confidence floor",
                      "no such gap")


def _register(root: pathlib.Path) -> pathlib.Path:
    d = root / "gaps"
    d.mkdir(parents=True)
    for i in (1, 2):
        (d / f"GAP-{i:03d}.json").write_text(
            json.dumps(dict(RECORD, id=f"GAP-{i:03d}")), encoding="utf-8")
    return d


@pytest.fixture()
def unsearchable_root(tmp_path):
    """A root holding a real register, then made readable-but-not-searchable."""
    root = tmp_path / "repo"
    _register(root)
    root.chmod(0o444)
    try:
        (root / "gaps").is_dir()
    except OSError:
        pass
    else:
        root.chmod(0o755)
        pytest.skip("mode 0o444 does not block stat here (root, or a permissive fs)")
    try:
        yield root
    finally:
        root.chmod(0o755)


def _expected(path: pathlib.Path) -> str:
    return f"Error: cannot read register directory: {path}"


def test_resolve_refuses_an_unanswerable_shape_probe(unsearchable_root):
    """The unit fact: `_resolve` raises the register's own error, naming the argument."""
    with pytest.raises(registry.RegistryError) as excinfo:
        _resolve(str(unsearchable_root))
    assert str(excinfo.value) == f"cannot read register directory: {unsearchable_root}"


@pytest.mark.parametrize("verb_args", [
    ["validate"], ["list"], ["list", "--json"], ["report"], ["prd"],
])
def test_every_register_verb_refuses_instead_of_publishing_zero_records(
        unsearchable_root, capsys, verb_args):
    code = main([verb_args[0], str(unsearchable_root), *verb_args[1:]])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.strip().splitlines()[-1] == _expected(unsearchable_root)
    assert not any(f in captured.err for f in FALSE_ATTRIBUTIONS)


def test_show_refuses_without_blaming_the_requested_id(unsearchable_root, capsys):
    code = main(["show", "GAP-001", str(unsearchable_root)])
    captured = capsys.readouterr()
    assert (code, captured.out) == (2, "")
    assert captured.err.strip().splitlines()[-1] == _expected(unsearchable_root)
    assert "no such gap" not in captured.err


def test_scan_refuses_before_walking_the_target(unsearchable_root, tmp_path, capsys):
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.py").write_text("x = 1\n", encoding="utf-8")
    code = main(["scan", str(target), "--gaps", str(unsearchable_root)])
    captured = capsys.readouterr()
    assert (code, captured.out) == (2, "")
    assert captured.err.strip().splitlines()[-1] == _expected(unsearchable_root)


@pytest.mark.parametrize("blocked_side", ["old", "new"])
def test_diff_refuses_from_either_side(unsearchable_root, tmp_path, capsys,
                                       blocked_side):
    """Neither ordering may read as "everything was added" or "everything removed"."""
    readable = tmp_path / "other"
    _register(readable)
    args = ([str(unsearchable_root), str(readable / "gaps")] if blocked_side == "old"
            else [str(readable / "gaps"), str(unsearchable_root)])
    code = main(["diff", *args])
    captured = capsys.readouterr()
    assert (code, captured.out) == (2, "")
    assert captured.err.strip().splitlines()[-1] == _expected(unsearchable_root)


def test_a_readable_root_still_resolves_to_its_nested_gaps_dir(tmp_path):
    """The control: the probe's ANSWERABLE outcomes are untouched."""
    root = tmp_path / "repo"
    d = _register(root)
    assert _resolve(str(root)) == d
    assert _resolve(str(d)) == d
    assert _resolve(str(tmp_path / "missing")) == tmp_path / "missing"


def test_the_refusal_sentence_has_exactly_one_source_in_src():
    """`registry.unreadable` is the ONE constructor: a second dialect cannot ship.

    Two sites raise this refusal (`registry._record_paths`, `cli._resolve`); the text
    is spelled once, in the constructor, so the published `Error: ` vocabulary keeps
    one dialect per failure no matter which door notices first.
    """
    src = pathlib.Path(registry.__file__).resolve().parent
    spellings = {p.name: p.read_text(encoding="utf-8").count(
        "cannot read register directory") for p in sorted(src.glob("*.py"))}
    assert sum(spellings.values()) == 1, spellings
    assert spellings["registry.py"] == 1, spellings
