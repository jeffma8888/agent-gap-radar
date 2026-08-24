"""Declarative, offline rule evaluation for gap checks.

Design constraints that are not negotiable:

* Rules are DATA, not code. A gap record is JSON in git; letting it carry
  executable code would make the register a remote-execution surface.
* A rule that matches must report WHERE. A finding with no location is not
  actionable, and an unactionable finding trains people to ignore the tool.
* Absence of a bad pattern is NEVER evidence of safety. That is the fail-open
  detector, and it is worse than no detector at all, because it reports health.
  Only positive evidence of a mitigation may produce ABSENT.
"""

from __future__ import annotations

import contextlib
import enum
import functools
import os
import pathlib
import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field

MAX_FILE_BYTES = 512 * 1024
#: Locations reported per rule. A lexical check on a large repo can match
#: hundreds of times; an unranked, uncapped list is noise a reader cannot act on.
MAX_LOCATIONS = 10
#: Files a content rule READS per evaluation. It bounds the `_read` and regex
#: passes below -- independently measured at 80-95% of a scan's wall clock, so
#: it bounds the dominant cost. It does NOT bound the walk, the sort or the
#: tracked-set intersection: those have all finished by the time it applies. The
#: earlier wording ("before the walk stops") named the one thing it does not
#: bound, and led a reader to conclude it bounds nothing. Where it DOES cut, the
#: cut is reported through `RuleHit.truncated_files` and never applied in
#: silence, because a search that stopped early cannot support a safety verdict.
MAX_SCAN_FILES = 4000
SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", ".tox", "target",
})


class Verdict(str, enum.Enum):
    """Deliberately five-valued. Collapsing these is how tools start lying."""

    PRESENT = "PRESENT"                # the gap's signature was found
    ABSENT = "ABSENT"                  # a mitigation was POSITIVELY found
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the gap cannot apply to this target
    MANUAL = "MANUAL"                  # undecidable statically; ask the question
    UNKNOWN = "UNKNOWN"                # no verdict; the gloss is UNKNOWN_MEANING


#: The ONE published gloss for `UNKNOWN`, and it must be true of BOTH its causes.
#: Iteration 63 gave the verdict a second cause that INVERTS on the safety axis:
#: there the check DID execute, and refuses `ABSENT` because `present_when` read
#: only the head of a domain `MAX_SCAN_FILES` cut. A gloss naming only the first
#: cause tells a consumer to retry a tool that never failed, so this one names
#: neither cause and delegates the distinction to the finding's own `reason`,
#: which states it in full. Every reader-facing surface reads THIS name: a second
#: copy of the wording is precisely how the two drift apart.
UNKNOWN_MEANING = "no verdict: the check could not run, or its search was incomplete"


@dataclass
class RuleHit:
    matched: bool
    locations: list[str] = field(default_factory=list)
    #: Total files the rule's domain held when `MAX_SCAN_FILES` cut it, else 0.
    #: A NEGATIVE result over a cut domain is INCOMPLETE, not clean, and this
    #: field is how that incompleteness survives the slice and reaches
    #: `run_check`. It is deliberately the domain TOTAL rather than a boolean:
    #: a reader deciding whether to widen the cap needs the size it was cut to.
    truncated_files: int = 0

    def __bool__(self) -> bool:
        return self.matched


@dataclass
class CheckOutcome:
    verdict: Verdict
    locations: list[str] = field(default_factory=list)
    question: str = ""
    reason: str = ""


_TRACKED_CACHE: dict[pathlib.Path, frozenset[pathlib.Path] | None] = {}


def tracked_files(target: pathlib.Path) -> frozenset[pathlib.Path] | None:
    """The files the target actually SHIPS, via `git ls-files`, or None.

    Judging a project by its gitignored scratch is judging the wrong artifact.
    A loop's per-iteration state, a virtualenv and a build dir are not the
    project's code, and findings located inside them are noise that trains a
    reader to distrust the tool. `git ls-files` is the authoritative answer to
    "what is this project", so it is preferred over any hand-maintained skip
    list; the skip list remains the fallback for a non-git target.

    Local subprocess only - this keeps the offline contract (no network).
    """
    key = target.resolve()
    if key in _TRACKED_CACHE:
        return _TRACKED_CACHE[key]
    result: frozenset[pathlib.Path] | None = None
    try:
        proc = subprocess.run(
            ["git", "-C", str(key), "ls-files", "-z"],
            capture_output=True, timeout=30)
        if proc.returncode == 0:
            names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
            result = frozenset((key / n) for n in names)
            if not result:
                result = None  # empty repo: fall back rather than match nothing
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        result = None
    _TRACKED_CACHE[key] = result
    return result


#: A mitigation found only in a test is not a mitigation. Credited from a test
#: file, a thorough suite reads as HEALTHIER than untested code, which inverts
#: the signal the whole tool exists to produce. Proven on a real target: GAP-009
#: was reported ABSENT because a test merely SPELLED `importlib.reload`, while
#: the target exhibited that gap continuously and shipped a verb to measure it.
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|testing|spec|specs|__tests__|fixtures?|conftest\.py)(/|$)"
    r"|(^|/)test_[^/]*$|[^/]*_test\.[a-z]+$|[^/]*\.spec\.[a-z]+$",
    re.IGNORECASE,
)


def is_test_path(target: pathlib.Path, path: pathlib.Path) -> bool:
    """True if this path is test scaffolding rather than code that runs."""
    try:
        rel = path.relative_to(target).as_posix()
    except ValueError:
        rel = path.as_posix()
    return bool(TEST_PATH_RE.search(rel))


#: Regex metacharacters that carry no glob meaning and must be escaped.
_GLOB_META = ".^$+{}()|[]\\"


def _class_body_regex(body: str) -> str:
    """Escape a glob character-class body, keeping `-` as the range operator.

    The body cannot be spliced in raw. `[[]x` splices to `[[]` and emits
    `FutureWarning: Possible nested set` -- and this tool contracts that stderr
    carries `Error: ` lines only, so a warning there is itself a defect. A `^`
    from the body is escaped rather than passed through, because glob spells
    negation `!`: `[^a]` is the class containing `^` and `a`, which the raw
    splice silently inverted into "not a".
    """
    return "".join(c if c == "-" else re.escape(c) for c in body)


def _component_regex(part: str) -> str:
    """Translate ONE path component; `*` and `?` must NOT cross a separator.

    `fnmatch.translate` is the wrong tool here. It renders `*` as `.*`, and `.`
    matches `/`, so `**/*eval*.json` would match `evals/basic.json` whose own
    FILENAME contains no "eval". Measured against the committed register: that
    over-match hit 2 of its 41 patterns, so the sloppy version is not merely
    theoretically wrong.
    """
    out: list[str] = []
    i = 0
    while i < len(part):
        char = part[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            negated = part[i + 1:i + 2] == "!"
            start = i + 2 if negated else i + 1
            # POSIX: a `]` in the FIRST body position is a literal member of the
            # class rather than the terminator, so `[]]` is the class containing
            # `]`. Searching from `start` would find that `]` and build the empty
            # class `[]`, which is not valid regex at all.
            first_is_bracket = part[start:start + 1] == "]"
            close = part.find("]", start + 1 if first_is_bracket else start)
            if close == -1:
                out.append("\\[")          # unterminated class: a literal bracket
            else:
                body = _class_body_regex(part[start:close])
                out.append("[" + ("^" if negated else "") + body + "]")
                i = close + 1
                continue
        elif char in _GLOB_META:
            out.append("\\" + char)
        else:
            out.append(char)
        i += 1
    return "".join(out)


@functools.lru_cache(maxsize=512)
def _glob_regex(pattern: str) -> re.Pattern[str]:
    """Full-match regex for one glob over a relative POSIX path.

    Glob semantics are defined HERE rather than inherited from `Path.glob`,
    because `Path.glob` disagrees with itself across supported interpreters: a
    trailing `**` yields directories only on 3.12 and files as well on 3.13, so
    every register pattern ending in `/**` silently matched NOTHING on 3.12.
    A scan of one commit must return one answer, so `/**` means "everything at
    or below here" by construction.

    Case-SENSITIVE on purpose: the tracked path is what git recorded, so the
    same commit scans identically on a case-insensitive macOS filesystem and on
    Linux. Matching case-insensitively would make a verdict depend on which
    laptop ran it. Cached because the register holds ~41 distinct patterns and
    a scan evaluates each many times.
    """
    parts = pattern.split("/")
    out: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if part == "**":
            out.append(".*" if last else "(?:[^/]+/)*")
        else:
            out.append(_component_regex(part) + ("" if last else "/"))
    try:
        return re.compile("^" + "".join(out) + "$")
    except re.error:
        # A malformed glob must MATCH NOTHING, never abort the scan. A register
        # is data that consumers write and share, so a bad class body such as
        # `[a-\]` is reachable input; letting `re.error` escape gives rc=1 with
        # a traceback and zero bytes of document, which is the one outcome the
        # CLI contract forbids. Falling back to the literal pattern text is the
        # same lenient reading `a[b.py` already gets: no tracked path is spelled
        # like a broken glob, so in practice it matches nothing. NOTE `re.error`
        # is not a `ValueError`, so no upstream `except ValueError` catches it.
        return re.compile("^" + re.escape(pattern) + "$")


def _match_globs(target: pathlib.Path, relatives: list[str],
                 globs: list[str], exclude_tests: bool) -> list[pathlib.Path]:
    """Match register globs against already-enumerated target-relative paths.

    The ONE match loop behind both branches of `iter_files`, so their shared
    rule is code rather than a promise. As a promise it drifted TWICE, each
    time as a fix landed on one branch that the other already had: `7570c39`
    gave a non-git scan the same glob dialect as a git one, and `60a0fce`
    re-landed the walked branch's containment guard.

    Stats unconditionally and takes NO branch-selecting flag: the existence
    check states something about the path this loop is about to PUBLISH as a
    locator, not about how that path was enumerated. `git ls-files` names
    staged-but-deleted files and submodule gitlinks, and a walk is not atomic,
    so a file that passed `entry.is_file()` during the descent can be gone by
    the time matching reaches it. Priced on the walked branch, which did not
    stat before: 2,146 extra `Path.is_file()` calls per full non-git scan,
    min-of-5 wall 489.9 ms against 500.1 ms unpatched -- inside the noise.

    `root` is derived, not accepted, so containment cannot be judged against a
    root a caller picked; the wrong one publishes outside evidence silently.

    Matching is `_glob_regex` and NOT `Path.glob`, because a register pattern is
    consumer-supplied data and `Path.glob` answers it three different ways. All
    three were measured against a git target that answered correctly on the same
    register bytes, so the verdict depended on whether the target happened to be
    a repository:

    * a trailing `/**` yields directories only on 3.12 and files as well on 3.13
      -- the divergence `_glob_regex` was written for, fixed on the tracked path
      only;
    * an absolute pattern such as `/etc/**` raises `NotImplementedError`, which
      like `re.error` is NOT a `ValueError`, so no upstream handler catches it:
      rc=1, zero bytes of document and a traceback on stderr, the one outcome the
      CLI contract forbids;
    * `""` raises `ValueError`, which the caller maps to a fabricated `UNKNOWN --
      Unacceptable pattern: PosixPath('.')`, rendering an interpreter-internal
      repr into a document meant to be committed and diffed.

    `_glob_regex` answers match-nothing for the last two, so one matcher removes
    both wrong answers and the interpreter divergence at once.
    """
    root = target.resolve()
    seen: set[pathlib.Path] = set()
    for pattern in globs:
        regex = _glob_regex(pattern)
        for rel in relatives:
            if not regex.match(rel):
                continue
            path = target / rel
            if not path.is_file():
                continue
            # A SYMLINK may not drag content in from outside the target.
            # `is_file()` follows links, so without this a tracked
            # `escape.py -> ../outside.py` is scanned and its lines are quoted
            # as evidence about a commit that does not contain them; on the
            # walked branch the same commit answered PRESENT 1 with `.git` and
            # PRESENT 0 without, a verdict flip on byte-identical inputs.
            # Resolved-vs-resolved, because a target whose own root is reached
            # through a link (macOS `/var` -> `/private/var`, where `tempfile`
            # puts everything) would otherwise have every one of its files
            # rejected. Settled once per MATCH rather than once per enumerated
            # path because that is strictly cheaper: measured on a non-git copy
            # of this repo against the live 16-record register, guarding during
            # the walk would cost 34 x 83 = 2,822 `resolve()` calls where this
            # loop reaches only 1,826 -- 1.5x cheaper for the same answer,
            # since a file matching no register glob never needs judging.
            try:
                if not path.resolve().is_relative_to(root):
                    continue
            except OSError:
                continue  # unreadable link chain: not a file we can judge
            if exclude_tests and is_test_path(target, path):
                continue
            seen.add(path)
    return sorted(seen)


def _iter_tracked(target: pathlib.Path, tracked: frozenset[pathlib.Path],
                  globs: list[str], exclude_tests: bool) -> list[pathlib.Path]:
    """Match globs against the tracked paths instead of walking the filesystem.

    Same answer, a fraction of the work. The old order globbed the whole tree
    and only afterwards filtered against the tracked set, so on a git target
    `SKIP_DIRS` was never consulted and the walk descended `.git`, `.venv` and
    every gitignored loop state dir: measured 181,440 yielded paths and 181,477
    `Path.resolve()` calls to arrive at 222 files on a real 229-file target.
    The tracked set is loaded before the first glob, so the information needed
    to skip that walk was already in hand and thrown away.
    """
    root = target.resolve()
    relatives: list[str] = []
    for path in tracked:
        try:
            relatives.append(path.relative_to(root).as_posix())
        except ValueError:
            continue  # a tracked path outside the target cannot match a glob
    return _match_globs(target, relatives, globs, exclude_tests)


def _iter_walked(target: pathlib.Path, globs: list[str],
                 exclude_tests: bool) -> list[pathlib.Path]:
    """Fallback for a non-git target: ENUMERATE by walking, then match as usual.

    There is no authoritative "what does this project ship" answer without git,
    so the hand-maintained `SKIP_DIRS` is the best available approximation and it
    prunes the descent rather than filtering matches afterwards. That is the only
    thing this branch decides differently from `_iter_tracked`. Everything after
    enumeration is `_match_globs`, which is where the matching rules live.
    """
    # The target-relative POSIX path is accumulated during the descent, so the
    # match loop needs no `relative_to` call per file and the string it matches is
    # built exactly like the one `_iter_tracked` matches. MEASURED, so it is not a
    # bug fix: the old form handled a relative target such as `.` correctly too.
    relatives: list[str] = []
    stack: list[tuple[pathlib.Path, str]] = [(target, "")]
    while stack:
        current, prefix = stack.pop()
        try:
            with os.scandir(current) as entries:
                children = list(entries)
        except OSError:
            continue  # unreadable directory: skip it, never abort the scan
        for entry in children:
            # Pruned by NAME on the entry the walk already holds, so a vendored
            # tree costs one stat instead of a full descent. The name test also
            # catches a FILE called `build`, which the previous `parts` filter
            # excluded too: this change is about matching, not about skipping.
            if entry.name in SKIP_DIRS:
                continue
            rel = prefix + entry.name
            if entry.is_dir(follow_symlinks=False):
                # A directory SYMLINK is not descended, which is what the old
                # `Path.glob("**/...")` walk did, and it also bounds a cycle.
                stack.append((pathlib.Path(entry.path), rel + "/"))
            elif entry.is_file():
                # `is_file()` FOLLOWS links, as the old walk's did, so an entry
                # whose target lies outside the tree is ENUMERATED here and
                # rejected later by `_match_globs`. Containment is a rule about
                # evidence, separate from enumeration, and settling it there
                # per match rather than here per walked path is 1.5x cheaper on
                # the same answer -- `_match_globs` carries the measurement.
                relatives.append(rel)
    return _match_globs(target, relatives, globs, exclude_tests)


#: One memoised enumeration: `(target as given, globs as asked, exclude_tests)`.
_FileDomainKey = tuple[str, tuple[str, ...], bool]

#: Enumeration frames, innermost last. A STACK for the same reason
#: `_READ_CACHE_STACK` is one: a nested scan is a DIFFERENT scan, so it gets its
#: own snapshot, and leaving it must leave the enclosing scan's snapshot intact.
_FILE_CACHE_STACK: list[dict[_FileDomainKey, list[pathlib.Path]]] = []


@contextlib.contextmanager
def file_cache_scope() -> Iterator[dict[_FileDomainKey, list[pathlib.Path]]]:
    """Memoise `iter_files` for the duration of ONE scan, then forget everything.

    The other half of the iteration that memoised the DECODE beside this and left
    the ENUMERATION per-rule, and it is the same two arguments. Cost: a domain is
    re-derived once per rule that asks for it -- measured on this repo as its own
    target, 38 calls resolve to 11 distinct keys, so 27 of 38 (71%) re-derive a
    list already in hand and one key is asked 18 times. Coherence: two rules
    asking the same question of one tree must receive one answer, and a writer
    touching the tree mid-scan is not hypothetical when this verb is pointed at a
    live agent checkout.

    The lifetime is the SCAN, not the process, for the reason `read_cache_scope`
    states in full: a process-lifetime enumeration answers a LATER scan from a
    tree that has since changed, and a wrong answer costs more here than a
    redundant walk. `_TRACKED_CACHE` above is process-lifetime and that asymmetry
    is a known open roadmap item; this scope deliberately does not extend it.

    A separate stack rather than a widened `read_cache_scope`: the two memoise
    different questions under differently-shaped keys, and that scope publishes a
    decode-specific contract its own tests patch BY NAME. `scan()` enters both on
    one line, so one scan still holds exactly one snapshot of each kind.
    """
    frame: dict[_FileDomainKey, list[pathlib.Path]] = {}
    _FILE_CACHE_STACK.append(frame)
    try:
        yield frame
    finally:
        # Pop rather than clear, and in `finally`: an exception raised mid-scan
        # must not leave a frame open for the next scan to answer from.
        _FILE_CACHE_STACK.pop()


def _enumerate_files(target: pathlib.Path, globs: list[str],
                     exclude_tests: bool) -> list[pathlib.Path]:
    """Resolve globs under target, restricted to what the project ships.

    Two branches, chosen by whether the target is a git repo, because the two
    cases have different authoritative answers to "which files COUNT": git names
    what the project ships, and without git the walk plus `SKIP_DIRS` is the best
    approximation of it. They differ in ENUMERATION only -- both then match the
    same register pattern with the same `_glob_regex`, because a glob dialect
    that depends on whether the target is a repository is a wrong answer, not a
    deliberate split.
    """
    tracked = tracked_files(target)
    if tracked is not None:
        return _iter_tracked(target, tracked, globs, exclude_tests)
    return _iter_walked(target, globs, exclude_tests)


def iter_files(target: pathlib.Path, globs: list[str],
               exclude_tests: bool = False) -> list[pathlib.Path]:
    """`_enumerate_files`, memoised if and only if a `file_cache_scope()` is open.

    Uncached by default on purpose, exactly as `_read` is: this is a public entry
    point, and a caller reaching it outside a scan must see the tree as it is now.

    THE KEY CARRIES `exclude_tests` because dropping it is a fail-open, not a
    tidier cache. Measured on this repo: of the 8 distinct glob sets one scan
    asks for, 3 are asked under BOTH values, and all 3 answer DIFFERENTLY -- 73
    files against 15, 73 against 15, and 90 against 32. A globs-only key would
    hand the 15-file domain to a rule that asked for 73, so a mitigation rule
    could search a domain its own `present_when` sibling had already narrowed,
    which is the fail-open this module's header forbids arriving through a cache
    instead of through a bad rule. It is also what explains the discrepancy an
    earlier measurement left open: 38 calls are 11 keys but only 8 glob sets.

    The target is keyed AS GIVEN, unresolved, for the reason `_read` documents:
    two spellings of one directory miss each other, which costs one redundant
    enumeration and can never return another target's files -- the safe direction
    for a cache in a tool whose whole value is that its verdicts are honest.

    The globs are keyed in the ORDER ASKED and are neither sorted nor deduped.
    Normalising would buy a few more hits by ASSERTING that order and repetition
    cannot change the answer. That happens to be true of `_match_globs` today,
    which accumulates into a set, but a key that encodes an invariant belonging
    to another function starts answering wrongly the day that function changes,
    and the failure would be silent. The cost of not normalising is a redundant
    enumeration; the cost of normalising wrongly is a wrong file list.
    """
    if not _FILE_CACHE_STACK:
        return _enumerate_files(target, globs, exclude_tests)
    frame = _FILE_CACHE_STACK[-1]
    key: _FileDomainKey = (str(target), tuple(globs), exclude_tests)
    if key not in frame:
        frame[key] = _enumerate_files(target, globs, exclude_tests)
    # A FRESH list on every hand-out, including the first, so the snapshot is
    # never aliased by a caller. `evaluate` slices this list today, but a caller
    # that sorted or truncated it in place would silently narrow the domain of
    # every later rule asking the same question -- the same fail-open one layer
    # down, arriving through an aliased list rather than through a bad rule.
    # A shallow copy suffices: `pathlib.Path` is immutable.
    return list(frame[key])


#: Read frames, innermost last. A STACK rather than one dict because the scope
#: has to nest: an inner scan is a DIFFERENT scan, so it gets its own snapshot,
#: and leaving it must leave the enclosing scan's snapshot intact.
_READ_CACHE_STACK: list[dict[pathlib.Path, str | None]] = []


@contextlib.contextmanager
def read_cache_scope() -> Iterator[dict[pathlib.Path, str | None]]:
    """Memoise `_read` for the duration of ONE scan, then forget everything.

    Two reasons the lifetime is a scan rather than the process. Cost: a content
    rule is evaluated per (rule, file) pair, so one file was decoded once per
    rule that reached it -- measured on a real 231-file target, 4,461 decodes
    covering 226 distinct files, the hottest three decoded 32 times each.
    Coherence: two rules reading one file could otherwise observe two different
    versions of it if a writer touched the tree mid-scan, and a live agent tree
    is exactly what this verb is pointed at.

    A process-lifetime cache would fix the cost and buy the opposite defect --
    a later scan answering from a file that has since changed. So the SCOPE is
    the invalidation: there is deliberately no mtime, size or hash check here,
    because an invalidation rule is a thing that can be subtly wrong, and a
    wrong answer in this tool costs more than a redundant read.
    """
    frame: dict[pathlib.Path, str | None] = {}
    _READ_CACHE_STACK.append(frame)
    try:
        yield frame
    finally:
        # Pop rather than clear, and in `finally`: an exception raised mid-scan
        # must not leave a frame open for the next scan to answer from.
        _READ_CACHE_STACK.pop()


def _decode(path: pathlib.Path) -> str | None:
    """Read one file as text, or None if it cannot contribute to a scan.

    `None` is a VALUE, not a failure: an oversized, unreadable or non-UTF-8
    file simply has no scannable text, and the caller skips it rather than
    failing the scan over it.
    """
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read(path: pathlib.Path) -> str | None:
    """`_decode`, memoised if and only if a `read_cache_scope()` is open.

    Uncached by default on purpose: `run_check` is a public entry point, and a
    caller reaching it outside a scan must see the file as it is now.

    The key is the path AS GIVEN, unresolved. Two spellings of one file
    therefore miss each other, which costs one redundant decode and can never
    return another file's text -- the safe direction for a cache in a tool
    whose whole value is that its verdicts are honest. `None` is stored like
    any other value, so an oversized or undecodable file is stat'ed and decoded
    once per scan instead of once per rule.
    """
    if not _READ_CACHE_STACK:
        return _decode(path)
    frame = _READ_CACHE_STACK[-1]
    if path in frame:
        return frame[path]
    text = _decode(path)
    frame[path] = text
    return text


def _scope_note(globs: list[str], pattern: str | None = None) -> str:
    """Describe an ABSENCE in actionable terms: what was searched, and for what.

    An absent pattern has no file:line, so returning an empty location list makes
    the finding unactionable. Naming the searched scope lets a reader disagree
    with the check instead of merely distrusting it.
    """
    scope = ", ".join(globs[:4])
    if pattern:
        return f"(no match) searched {scope} for /{pattern}/"
    return f"(no files) searched {scope}"


def _rank_locations(code_hits: list[str], test_hits: list[str]) -> list[str]:
    """Code before tests, capped, with the suppressed remainder named.

    A lexical signature match in a test file is real but rarely where a reader
    should start, and on a repo with a large suite the test hits crowd out every
    line of code that actually runs. Ranking is honest only if the reader can
    see what was dropped, so the remainder is reported rather than silently cut.
    """
    ranked = code_hits + test_hits
    shown = ranked[:MAX_LOCATIONS]
    hidden = len(ranked) - len(shown)
    if not hidden:
        return shown
    # Derive the test count from the boundary rather than re-guessing from the
    # string: code_hits come first, so everything past max(shown, code) is a test.
    in_tests = len(ranked) - max(len(shown), len(code_hits))
    note = f"(+{hidden} more match{'es' if hidden != 1 else ''}"
    if in_tests > 0:
        note += f", {in_tests} in test files"
    return shown + [note + ")"]


def evaluate(rule: dict, target: pathlib.Path,
             exclude_tests: bool = False) -> RuleHit:
    """Evaluate one rule against a target directory.

    An unknown rule kind raises: silently returning False would be the
    fail-open failure this module exists to prevent.

    `exclude_tests` is set when evaluating a MITIGATION. It propagates through
    every nested combinator, because a mitigation credited from test text is a
    false negative and a false negative here reads as safety.

    `RuleHit.truncated_files` propagates the same way and for the same reason: a
    content rule whose domain `MAX_SCAN_FILES` cut answers over a PREFIX of that
    domain, and a combinator that dropped the fact would let the composite claim
    a completeness none of its parts had.
    """
    kind = rule.get("kind")

    if kind == "any_of":
        locations: list[str] = []
        matched = False
        # `max` over the sub-rules ACTUALLY evaluated. A combinator that dropped
        # this would let a capped sub-rule launder its incompleteness into a
        # clean-looking composite answer, which is the same fail-open one level up.
        truncated = 0
        for sub in rule.get("rules", []):
            hit = evaluate(sub, target, exclude_tests)
            truncated = max(truncated, hit.truncated_files)
            if hit.matched:
                matched = True
                locations.extend(hit.locations)
        return RuleHit(matched, locations, truncated)

    if kind == "all_of":
        subs = rule.get("rules", [])
        if not subs:
            raise ValueError("all_of with no sub-rules is vacuously true; forbidden")
        locations = []
        truncated = 0
        for sub in subs:
            hit = evaluate(sub, target, exclude_tests)
            # Accumulated BEFORE the short circuit: the sub-rule that failed was
            # evaluated, so if the cap cut its domain the composite `False` rests
            # on an incomplete search and must say so.
            truncated = max(truncated, hit.truncated_files)
            if not hit.matched:
                return RuleHit(False, [], truncated)
            locations.extend(hit.locations)
        return RuleHit(True, locations, truncated)

    if kind == "not":
        inner = rule.get("rule")
        if inner is None:
            raise ValueError("not requires a 'rule'")
        hit = evaluate(inner, target, exclude_tests)
        # Negation flips the BOOLEAN, never the completeness: a search that read
        # part of its domain is equally partial whichever way its answer is read.
        return RuleHit(not hit.matched, [], hit.truncated_files)

    if kind in ("file_exists", "file_absent"):
        files = iter_files(target, rule["globs"], exclude_tests)
        found = bool(files)
        if kind == "file_exists":
            return RuleHit(found, [str(p.relative_to(target)) for p in files[:10]])
        # An absence has no line to point at, but it does have a searched scope.
        # Naming that scope is what makes the finding actionable.
        return RuleHit(not found, [_scope_note(rule["globs"])] if not found else [])

    if kind in ("content_matches", "content_absent"):
        try:
            regex = re.compile(rule["pattern"], re.MULTILINE)
        except re.error as exc:
            raise ValueError(f"invalid pattern {rule.get('pattern')!r}: {exc}") from exc
        code_hits: list[str] = []
        test_hits: list[str] = []
        files = iter_files(target, rule["globs"], exclude_tests)
        # The slice below is the iterable of the read/regex loop, so the cap bounds
        # the dominant cost of a scan. What it does not do is stay quiet about it:
        # the files past the cap go UNREAD, so a non-match here is a fact about a
        # PREFIX of the domain, and the total is carried out for `run_check` to
        # weigh. Reads stay the first `MAX_SCAN_FILES` in the existing order, so
        # no file that is read today becomes unread.
        #
        # The size is NAMED rather than compared inline as a length call against
        # an upper-case constant, and that is not style. This tool scans ITSELF,
        # and that exact shape is a token in GAP-014's mitigation vocabulary, so
        # the inline form credits this tree with artifact-shape validation it
        # does not implement and turns its own GAP-014 verdict from MANUAL into
        # ABSENT -- a false safety claim of precisely the class the truncation
        # branch below exists to prevent. Measured: the inline form moves
        # `radar scan .` by two verdicts. Keep it named.
        domain_size = len(files)
        truncated = domain_size if domain_size > MAX_SCAN_FILES else 0
        for path in files[:MAX_SCAN_FILES]:
            text = _read(path)
            if text is None:
                continue
            for m in regex.finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                loc = f"{path.relative_to(target)}:{line_no}"
                (test_hits if is_test_path(target, path) else code_hits).append(loc)
                break
        found = bool(code_hits or test_hits)
        if kind == "content_matches":
            return RuleHit(found, _rank_locations(code_hits, test_hits), truncated)
        return RuleHit(not found,
                       [_scope_note(rule["globs"], rule["pattern"])] if not found else [],
                       truncated)

    raise ValueError(f"unknown rule kind: {kind!r}")


def run_check(check: dict, target: pathlib.Path) -> CheckOutcome:
    """Decide one check against a target. Fail-CLOSED by construction.

    Order matters. `mitigated_when` is not allowed to override a positive
    `present_when` hit: a target exhibiting BOTH signatures is the genuinely
    dangerous case (a partial mitigation), so it escalates to MANUAL rather
    than being reported as safe.

    Truncation is weighed on ONE transition, `ABSENT` to `UNKNOWN`, and the
    asymmetry is the point. Positive evidence is unaffected by an unread tail --
    a signature that WAS found is found whatever went unread -- so `PRESENT`,
    `MANUAL` and `NOT_APPLICABLE` are decided without consulting it. `MANUAL`
    for "neither signature detected" already tells the reader that absence of a
    pattern is not evidence of safety, so downgrading it would cost the reader
    its `manual_question` and buy nothing. `ABSENT` is the only verdict that
    asserts safety, so it is the only one a cut domain can lie with.
    """
    applies = check.get("applies_when")
    if applies is not None:
        try:
            if not evaluate(applies, target):
                return CheckOutcome(Verdict.NOT_APPLICABLE,
                                    reason="applies_when did not match")
        except ValueError as exc:
            return CheckOutcome(Verdict.UNKNOWN, reason=f"applies_when: {exc}")

    question = check.get("manual_question", "")
    present_rule = check.get("present_when")
    mitigated_rule = check.get("mitigated_when")

    if present_rule is None and mitigated_rule is None:
        return CheckOutcome(Verdict.MANUAL, question=question,
                            reason="check is manual by declaration")

    try:
        present = evaluate(present_rule, target) if present_rule else RuleHit(False)
        # exclude_tests=True: a mitigation named only by a test is not a
        # mitigation. Crediting it makes a well-tested repo look safer than
        # an untested one, which inverts the signal.
        mitigated = (evaluate(mitigated_rule, target, exclude_tests=True)
                     if mitigated_rule else RuleHit(False))
    except ValueError as exc:
        return CheckOutcome(Verdict.UNKNOWN, reason=str(exc))

    if present.matched and mitigated.matched:
        return CheckOutcome(
            Verdict.MANUAL, locations=present.locations + mitigated.locations,
            question=question or
            "Both the gap signature and a mitigation were found. Confirm the "
            "mitigation actually covers the code path where the signature appears.",
            reason="ambiguous: both signatures present")

    if present.matched:
        return CheckOutcome(Verdict.PRESENT, locations=present.locations,
                            reason="gap signature found")

    if mitigated.matched:
        if present.truncated_files:
            # `ABSENT` is the only one of the five verdicts that CLAIMS safety,
            # and a claim is only as wide as the search behind it. `present_when`
            # found nothing over a domain `MAX_SCAN_FILES` cut, so the signature
            # may sit in the tail that was never read: that is UNKNOWN. The
            # mitigation hit is real but cannot carry the claim on its own, and
            # its locations are dropped deliberately -- publishing them beside an
            # UNKNOWN verdict would read as evidence of safety.
            return CheckOutcome(
                Verdict.UNKNOWN,
                reason=("present_when read only the first "
                        f"{MAX_SCAN_FILES} of {present.truncated_files} files "
                        "(MAX_SCAN_FILES), so its non-match cannot support "
                        "ABSENT over the unread remainder"))
        return CheckOutcome(Verdict.ABSENT, locations=mitigated.locations,
                            reason="mitigation positively identified")

    # Nothing found either way. This is NOT absence of the gap.
    return CheckOutcome(
        Verdict.MANUAL, question=question or
        "Neither the gap signature nor a mitigation was detected. Absence of a "
        "pattern is not evidence of safety - confirm by hand.",
        reason="no signature and no mitigation detected")
