"""Load and validate gap records from a directory of JSON files."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable

from pydantic import ValidationError

from .models import Gap


class RegistryError(Exception):
    """Raised when the register on disk is not loadable or not self-consistent."""


def gaps_dir(root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(root) / "gaps"


def unreadable(d: pathlib.Path | str) -> RegistryError:
    """The ONE constructor for "this register directory cannot be read".

    Two sites raise it -- `_record_paths` when the listing itself fails, and
    `cli._resolve` when the nested-`gaps/` probe is unanswerable -- and neither may
    spell the sentence: the text is pinned, so one failure keeps one dialect in the
    published `Error: ` vocabulary no matter which door notices first. Returns the
    exception instead of raising it, so each caller keeps its own `from exc` chain,
    and the errno is deliberately not quoted -- `cli` publishes this string verbatim
    and the directory already names itself.
    """
    return RegistryError(f"cannot read register directory: {d}")


def _record_paths(d: pathlib.Path) -> list[pathlib.Path]:
    """Every `*.json` entry of `d`, sorted, or refuse because `d` cannot be listed.

    This exists because the obvious spelling -- `sorted(d.glob("*.json"))` -- is
    FAIL-OPEN at the register's front door: `pathlib.Path.glob` swallows a
    directory-level `OSError` and yields nothing, so a register whose DIRECTORY is
    unreadable arrives at every caller as a register holding zero records. The
    asymmetry that made it a defect rather than a taste question is measured in both
    directions over the same files: unreadable FILES inside a readable directory are
    already reported as problems below, one clause each, while the same files behind
    an unreadable directory were a silent success. `d.is_dir()` cannot catch it --
    it returns True on a mode-`0o000` directory -- so the listing must be ATTEMPTED,
    which is why this enumerates with `iterdir()` and converts the failure instead of
    inspecting `st_mode` bits or asking `os.access`: both answer a different question
    than "can I list this".

    Filtering on the `.json` suffix reproduces `glob("*.json")` exactly, hidden names
    included, so no readable register's record set moves.
    """
    try:
        entries = [path for path in d.iterdir() if path.name.endswith(".json")]
    except OSError as exc:
        raise unreadable(d) from exc
    return sorted(entries)


def load_all(directory: pathlib.Path | str) -> list[Gap]:
    """Load every *.json in `directory`, sorted by filename for determinism."""
    d = pathlib.Path(directory)
    if not d.is_dir():
        raise RegistryError(f"not a directory: {d}")

    gaps: list[Gap] = []
    problems: list[str] = []
    for path in _record_paths(d):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: unreadable/invalid JSON: {exc}")
            continue
        try:
            gaps.append(Gap.model_validate(raw))
        except ValidationError as exc:
            problems.append(f"{path.name}: {exc.error_count()} schema error(s): "
                            f"{exc.errors()[0].get('msg', '?')}")

    ids = [g.id for g in gaps]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"duplicate gap id(s): {', '.join(dupes)}")

    if problems:
        raise RegistryError("; ".join(problems))
    return gaps


def select_one(gaps: Iterable[Gap], gap_id: str) -> Gap:
    """The one record named `gap_id`, or refuse naming it.

    Split out of `load_one` so a caller that ALREADY holds the register can narrow it
    without a second full load, and -- the reason it lives here rather than in `cli.py`
    -- so the sentence `no such gap: X` keeps exactly ONE construction site in this
    package. `radar prd --gap` and `radar scan --gap` refuse an unknown id with the same
    bytes because they run the same line, not because two strings happen to agree; a
    consumer matching that sentence cannot be told two stories about one input.

    Raises rather than returning `None`: every caller here turns the miss into a
    published `Error: ` line and exit 2, and an ignorable `None` is how a mistyped id
    silently becomes "the whole register".
    """
    for gap in gaps:
        if gap.id == gap_id:
            return gap
    raise RegistryError(f"no such gap: {gap_id}")


def load_one(directory: pathlib.Path | str, gap_id: str) -> Gap:
    return select_one(load_all(directory), gap_id)
