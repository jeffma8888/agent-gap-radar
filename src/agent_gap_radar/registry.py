"""Load and validate gap records from a directory of JSON files."""

from __future__ import annotations

import json
import pathlib

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


def load_one(directory: pathlib.Path | str, gap_id: str) -> Gap:
    for gap in load_all(directory):
        if gap.id == gap_id:
            return gap
    raise RegistryError(f"no such gap: {gap_id}")
