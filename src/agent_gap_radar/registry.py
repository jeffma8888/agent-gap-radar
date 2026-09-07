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


def load_all(directory: pathlib.Path | str) -> list[Gap]:
    """Load every *.json in `directory`, sorted by filename for determinism."""
    d = pathlib.Path(directory)
    if not d.is_dir():
        raise RegistryError(f"not a directory: {d}")

    gaps: list[Gap] = []
    problems: list[str] = []
    for path in sorted(d.glob("*.json")):
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
