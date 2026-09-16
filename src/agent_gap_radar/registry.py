"""Load and validate gap records from a directory of JSON files."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable
from typing import Any

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


def _counted_items(kind: str, items: list[str]) -> str:
    """`N <kind>: <item>{_ITEM_JOIN}<item>...` -- the ONE shape of a per-file clause.

    Both clauses this module composes for one refused file -- the schema one and the
    duplicate-key one below -- are a COUNT of what follows plus the items themselves,
    and the count is taken from `items` HERE rather than passed in by each caller, so
    a clause can never publish a head that disagrees with its own body. That is not a
    hypothetical: it is the exact defect iteration 242 fixed, where the head came from
    `exc.error_count()` and the body from a list that had dropped every error but the
    first. Each caller supplies only its own noun, so the two clauses cannot drift
    into two shapes for one job, and `_ITEM_JOIN` stays spelled once.
    """
    return f"{len(items)} {kind}: {_ITEM_JOIN.join(items)}"


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

    The count is derived from `items` by `_counted_items` rather than from
    `exc.error_count()` on purpose: head and body come from the SAME list, so the
    number can never again disagree with what follows it. Messages are pydantic's
    own, verbatim -- this renderer adds the locator and nothing else, because
    paraphrasing a validator's words is how the two dialects (`tools/promote.py`
    prints the full multi-error string) drifted apart in the first place.
    """
    items = [f"{_dotted_loc(err['loc'])}: {err.get('msg', '?')}" for err in exc.errors()]
    return _counted_items("schema error(s)", items)


def parse_record(text: str) -> Any:
    """One record file's JSON, REFUSED when any object in it repeats a key.

    WHY THIS EXISTS AND WHY IT IS NOT `json.loads`
    Python keeps the LAST of two identical keys and raises nothing, so ~40 appended
    bytes -- a second `"evidence"` array pasted after the first -- silently replace the
    ladder a record's confidence is DERIVED from, which is the one rule `VISION.md`
    names as the rule it protects and the quality bar's core invariant. Measured over
    the committed register before this was written: the doctored file is valid RFC 8259
    JSON and valid against the schema, so `radar validate` certified it at exit 0 while
    `radar report` moved that record out of the below-floor section into the ranked
    table at confidence 5 instead of 1. Both shipped doors called it clean. `gaps/` is
    the UNTRUSTED path by this repo's own account -- `tools/check_public_safety.py`
    documents it as written by an outside research pipeline from arbitrary primary
    sources -- so this is a live door, not a hypothetical one.

    WHY REPETITION AND NOT DISAGREEMENT
    Two byte-identical values refuse too. A file that answers a question twice has no
    single answer whatever the bytes say, and a rule keyed on the values differing
    would accept the shape while rejecting only the instances that happen to differ --
    which reads as "duplicates are fine" to whatever writes the next record.

    WHY THE PATHS ARE BUILT BOTTOM-UP
    `object_pairs_hook` is called once per object, innermost first, and it is told
    NOTHING about where that object sits in the document, so a dotted path cannot be
    built top-down. Each call therefore reports its own repeats relative to itself and
    ADOPTS what its children reported, prefixed by the key the child was reached
    through. `adopt` walks lists itself because `json` calls no hook for an array, and
    it walks EVERY pair rather than the deduplicated mapping, so a repeat nested inside
    the copy the parser is about to discard is still named.

    WHY THE PENDING MAP IS KEYED ON `id()` WITH A KEEPALIVE LIST
    A hook cannot return anything but the object it built if the parsed value is to
    stay a plain `dict` for pydantic, so the side channel has to be keyed on identity.
    Every registered object is also appended to `keepalive`, because the value of a
    discarded duplicate key becomes garbage the moment `dict(pairs)` drops it and CPython
    would be free to hand its `id()` to a later object -- which would attribute one
    file's repeats to the wrong path.

    `dict(pairs)` reproduces `json.loads` exactly for an accepted file -- first
    insertion position, last value -- so no register that loads today parses differently.

    Raises `RegistryError` carrying the CLAUSE only. The `<basename>: ` prefix belongs
    to the caller, exactly as it does for the schema clause, so a future second door
    (the `tools/` scripts of roadmap row 129) can reuse this refusal instead of growing
    a second dialect for one failure.
    """
    pending: dict[int, list[tuple[int | str, ...]]] = {}
    keepalive: list[object] = []

    def adopt(value: object) -> list[tuple[int | str, ...]]:
        """Repeat paths recorded anywhere inside `value`, relative to `value`."""
        if isinstance(value, dict):
            return pending.pop(id(value), [])
        if isinstance(value, list):
            return [(index, *below)
                    for index, item in enumerate(value)
                    for below in adopt(item)]
        return []

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj = dict(pairs)
        found: list[tuple[int | str, ...]] = []
        seen: set[str] = set()
        for key, value in pairs:
            if key in seen:
                found.append((key,))
            seen.add(key)
            found.extend((key, *below) for below in adopt(value))
        if found:
            pending[id(obj)] = found
            keepalive.append(obj)
        return obj

    parsed = json.loads(text, object_pairs_hook=hook)
    repeats = sorted({_dotted_loc(path) for path in adopt(parsed)})
    if repeats:
        raise RegistryError(_counted_items("duplicate JSON key(s)", repeats))
    return parsed


def load_all(directory: pathlib.Path | str) -> list[Gap]:
    """Load every *.json in `directory`, sorted by filename for determinism.

    The ONLY record-reading site under `src/`, which is what lets `parse_record`
    hold the strict-parse rule for the whole product from one line. Every failure a
    file can have -- unreadable, not JSON, a repeated key, a schema error -- becomes
    ONE clause naming that file, and the whole set is raised together, so a fixer
    reads every bad file per run rather than one per run.
    """
    d = pathlib.Path(directory)
    if not d.is_dir():
        raise RegistryError(f"not a directory: {d}")

    gaps: list[Gap] = []
    problems: list[str] = []
    for path in _record_paths(d):
        try:
            raw = parse_record(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: unreadable/invalid JSON: {exc}")
            continue
        except RegistryError as exc:
            # A SECOND branch rather than the free routing: the clause above would
            # catch this for nothing, because a hook that raised `ValueError` arrives
            # as one -- but the file IS readable and IS valid JSON, so that sentence
            # would name the wrong defect and tell a fixer nothing about which key to
            # delete. The record is not validated: a file that answers twice yields no
            # record to validate, so this file contributes exactly one clause.
            problems.append(f"{path.name}: {exc}")
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
