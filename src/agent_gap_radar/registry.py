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


#: Rendered in place of an EMPTY error `loc`. pydantic reports a RECORD-level failure
#: -- a `model_validator`, e.g. `_one_citation_is_resolvable` -- with `loc == ()`,
#: because the whole record is at fault rather than one of its fields. Without a token
#: that item would begin `": Value error, ..."`, and a consumer splitting an item on its
#: first `": "` could not tell a record-level failure from a field whose name is blank.
_RECORD_LEVEL_LOC = "<record>"

#: Separates the rendered errors of ONE record. Deliberately not `"; "`, which already
#: separates per-FILE blocks below AND occurs inside pydantic's own messages
#: (`unknown status 'opne'; allowed: (...)`): reusing it would make a nesting level
#: invisible instead of merely unsplittable.
_ITEM_JOIN = " | "


def _dotted_loc(loc: tuple[int | str, ...]) -> str:
    """One pydantic error `loc` as a dotted field path, or the record-level token.

    `("evidence", 0, "excerpt")` -> `evidence.0.excerpt`. List indices are rendered as
    BARE digits rather than `[0]` so the whole path stays one `.`-splittable token; every
    field name in this schema is an identifier, so a bare integer between two dots is
    unambiguously an index and needs no brackets to be read as one.
    """
    return ".".join(str(part) for part in loc) or _RECORD_LEVEL_LOC


def _schema_problem(exc: ValidationError) -> str:
    """EVERY error in a refused record, each named with the FIELD it occurred at.

    The ONE construction site of this product's schema-refusal sentence -- deliberately
    the only place its words are spelled, so a census over `src/` finds it once and a fix
    cannot become a second private copy. It exists because the obvious spelling --
    `error_count()` plus `errors()[0]["msg"]` -- was FAIL-QUIET at the door the register
    grows through: it printed a count it then contradicted, dropping every error after the
    first and, worse, dropping every `loc`. So `severity` going missing refused with a
    bare `Field required` naming no field, and an unknown key inside a citation refused
    with `Extra inputs are not permitted` -- a sentence that names neither the key, nor
    the field, nor which citation. `radar validate` is what CI gates and unattended
    research passes run, and neither can ask a follow-up question, so a fixer had to
    re-run the door once per error to discover errors two and three.

    The count is `len(items)` rather than `exc.error_count()` on purpose: head and body are
    then derived from the SAME list, so the number can never again disagree with what
    follows it. Messages are pydantic's own, verbatim -- this renderer adds the locator and
    nothing else, because paraphrasing a validator's words is how the two dialects
    (`tools/promote.py` prints the full multi-error string) drifted apart in the first place.
    """
    items = [f"{_dotted_loc(err['loc'])}: {err.get('msg', '?')}" for err in exc.errors()]
    return f"{len(items)} schema error(s): {_ITEM_JOIN.join(items)}"


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
            problems.append(f"{path.name}: {_schema_problem(exc)}")

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
