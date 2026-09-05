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

#: Folded (lower-cased) text frames, innermost last, one frame per open scan, and
#: kept SEPARATE from the read frames rather than added as a second value inside
#: them. `read_cache_scope()` yields its read frame to the caller, so widening that
#: object would change a published shape to buy an internal optimisation. One scope
#: owns both stacks, which is what keeps a fold from outliving the scan that made it.
_FOLD_CACHE_STACK: list[dict[pathlib.Path, str]] = []


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
    _FOLD_CACHE_STACK.append({})
    try:
        yield frame
    finally:
        # Pop rather than clear, and in `finally`: an exception raised mid-scan
        # must not leave a frame open for the next scan to answer from.
        #
        # Both frames are popped by the SAME `finally`, so the fold cache has
        # exactly the lifetime argued for above and a later scan can never answer
        # from a fold of a file that has since changed. Pushing them together and
        # popping them together is what makes that a structural property of the
        # scope rather than a rule a future caller has to remember.
        _READ_CACHE_STACK.pop()
        _FOLD_CACHE_STACK.pop()


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


def _folded(path: pathlib.Path, text: str) -> str:
    """`text.lower()`, memoised if and only if a `read_cache_scope()` is open.

    The fold serves the mandatory-literal prefilter in `evaluate`, which tests
    membership against lower-cased text. A content rule is evaluated per (rule,
    file) pair, so without memoisation one file is folded once per rule that
    reaches it and a scan pays for the same allocation many times over -- the same
    cost shape, and the same fix, as the decode `_read` memoises.

    Keyed on the path alone rather than on the text, which is sound only because
    the read is memoised by the SAME scope: inside one scan a path has exactly one
    text, so a path key cannot hand back the fold of another version of the file.

    Uncached by default for the reason `_read` is: outside a scan there is no key
    at all, the fold is computed and discarded, and the cache stays an
    optimisation rather than a precondition. `evaluate` answers identically with
    no scope open, only slower.
    """
    if not _FOLD_CACHE_STACK:
        return text.lower()
    frame = _FOLD_CACHE_STACK[-1]
    if path in frame:
        return frame[path]
    folded = text.lower()
    frame[path] = folded
    return folded


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
             exclude_tests: bool = False, *,
             boolean_only: bool = False) -> RuleHit:
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

    `boolean_only` is set by a caller that provably DISCARDS
    `RuleHit.locations`, and all it licenses is the guarded exit
    `content_absent` already takes: a `content_matches` node leaves its file
    loop once its own boolean can no longer change. It is KEYWORD-ONLY so it can
    never be mistaken for the positionally passed `exclude_tests` in a recursive
    call. This table is the entire safety argument, and it is exhaustive -- a
    True anywhere else would truncate a list a reader acts on:

    * `not` -> True for its inner rule, unconditionally. Its own return is
      `RuleHit(not matched, [], ...)`, so those locations are thrown away one
      line later whatever the inner rule computed.
    * `run_check`'s `applies_when` -> True. It is read only through
      `RuleHit.__bool__`, so nothing but the boolean escapes.
    * `any_of` / `all_of` -> the CALLER'S value, unchanged. They only forward
      locations upward, so they discard exactly when their caller discards.
    * `present_when` / `mitigated_when` -> nothing. Both publish their locations
      into a `CheckOutcome` that a reader opens, so a short list there would
      silently break the code-before-test ranking.

    Only `locations` can differ under the flag, and that is by construction
    rather than by care -- this propagation shape has already produced one
    fail-open in this module, so it is not enough for the flag to look safe.
    `matched` is monotone in the content loop (`found` reads
    `bool(code_hits or test_hits)` and nothing is ever removed from either), and
    `truncated_files` is derived from the domain size BEFORE the loop, so neither
    the verdict nor the completeness signal can move when the loop stops early.
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
            # `boolean_only` forwarded, never invented: this combinator hands its
            # sub-rules' locations straight up, so it discards them exactly when
            # its own caller does.
            hit = evaluate(sub, target, exclude_tests, boolean_only=boolean_only)
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
            hit = evaluate(sub, target, exclude_tests, boolean_only=boolean_only)
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
        # `boolean_only=True` UNCONDITIONALLY, and the line below is the proof
        # rather than a promise: this branch returns `[]`, so whatever list the
        # inner rule built is discarded here no matter who called `not`.
        hit = evaluate(inner, target, exclude_tests, boolean_only=True)
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
        # Proved ONCE per rule evaluation, because a mandatory-literal set is a
        # property of the pattern and not of any file. `None` means the extractor
        # could not prove one, and `None` is the fail-open-proof default: it skips
        # nothing, so every file under an unprovable pattern still pays its regex
        # pass and can never lose a verdict to this optimisation.
        #
        # The name is looked up as a module global at CALL time, which is this
        # repo established seam convention: a test substitutes the extractor to
        # prove that a skip is this guard decision rather than an accident
        # somewhere in the regex path.
        literals = required_literals(rule["pattern"])
        # Decided ONCE, above the loop: neither operand can change inside it, and
        # this loop is the exact cost term the flag exists to reduce, so paying for
        # the test per file would spend part of the saving on computing it.
        stop_at_first_hit = kind == "content_absent" or boolean_only
        for path in files[:MAX_SCAN_FILES]:
            text = _read(path)
            if text is None:
                continue
            if literals is not None:
                # Folded once into a local: the membership test below runs once per
                # literal, and re-deriving the fold inside that loop would pay for
                # it per literal instead of per file.
                folded = _folded(path, text)
                if not any(literal in folded for literal in literals):
                    # A text holding no member of a MANDATORY set cannot match, so
                    # the regex pass over it is provably wasted. The one-directional
                    # guarantee is the entire safety argument: a match IMPLIES some
                    # member is present, so a MISSING member is decisive while a
                    # present one proves nothing. This skip can therefore only ever
                    # drop a pass that would have found nothing; it cannot turn a
                    # match into a non-match, which is the inverted verdict -- the
                    # false claim of safety -- that this module exists to prevent.
                    #
                    # Placed after the read on purpose: the literal test needs the
                    # text, so no file that is read today becomes unread and
                    # `truncated` keeps meaning exactly what it meant.
                    continue
            for m in regex.finditer(text):
                # Counted over a BOUNDED RANGE, never over a copied prefix.
                # Slicing the text up to the hit allocates a fresh string as long
                # as that prefix, once per hit reported, to answer a question
                # `str.count` answers in place. Same number, no allocation.
                #
                # The slice form is deliberately not spelled anywhere in this file,
                # comments included: an acceptance check for its absence is a
                # substring test, and this tool scans ITSELF, so naming the banned
                # shape here would red that check from inside a comment.
                line_no = text.count("\n", 0, m.start()) + 1
                loc = f"{path.relative_to(target)}:{line_no}"
                (test_hits if is_test_path(target, path) else code_hits).append(loc)
                break
            if stop_at_first_hit and (code_hits or test_hits):
                # The answer is settled here and cannot change, so every further
                # read and regex pass computes a result that is provably discarded.
                # Two independent reasons the caller can no longer use more than
                # the boolean, and either one alone is sufficient:
                #
                # * `content_absent`, whose branch below reads this loop only
                #   through `bool(code_hits or test_hits)` -- monotone once
                #   anything has been appended -- and throws `locations` away.
                # * `boolean_only`, which the two sites in this module's own
                #   propagation table set only where the RESULT's locations are
                #   discarded in code a reader can follow.
                #
                # The exit still has to be EARNED rather than taken always,
                # because a `content_matches` node evaluated for its locations
                # publishes them: stopping there unasked would truncate the list
                # and silently break the code-before-test ranking. `truncated` is
                # derived from `domain_size` BEFORE this loop, so an exit here
                # still reports the same `MAX_SCAN_FILES` incompleteness an
                # unbroken loop reported -- a cut domain is never laundered into a
                # clean-looking answer.
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
            # `boolean_only=True`: this call is consumed by `not ...`, so only
            # `RuleHit.__bool__` is ever read and the location list cannot escape
            # into the `CheckOutcome` returned below.
            if not evaluate(applies, target, boolean_only=True):
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


# --- Required-literal extraction ---------------------------------------------
#
# A content rule proves ABSENCE the expensive way: `evaluate` compiles the
# pattern and runs it over every file in the rule's domain, so the budget is
# `patterns x corpus bytes` and it is spent overwhelmingly proving a pattern is
# NOT there. Rejecting a file without running the regex is the one lever on that
# term, and it needs a literal every match must contain.
#
# `evaluate`'s content branch is the only caller. The failure an unsound literal
# causes is the INVERTED one -- a skipped file turns a PRESENT into an ABSENT, a
# false claim of safety, which this module's header and VISION.md both forbid --
# so the extractor and its proof shipped one bite ahead of this call site.

#: Regex metacharacters. An UNESCAPED one of these ENDS a literal run, because
#: past it the characters a match must contain are no longer decidable one at a
#: time: `a*` requires no `a`, `[ab]` requires neither, `(x|y)` requires neither.
#: `}` and `]` outside their opener are literal to `re` and are still treated as
#: enders here -- over-conservatism costs one wasted regex pass, and only
#: under-conservatism costs a verdict. A backslash is absent because the escape
#: branch in `_leading_literal_run` consumes it before this set is consulted.
_RUN_ENDERS = frozenset(".^$*+?{}[]()|")

#: Escapes whose second character IS a character every match must contain.
#: Punctuation only, and that is the whole safety argument: `\b`, `\w`, `\d`,
#: `\s`, `\A`, `\1` and every other alphanumeric escape denote a CLASS, an
#: ASSERTION or a BACKREFERENCE, so reading one as a literal would invent a
#: requirement the pattern does not have -- the fail-open direction.
_LITERAL_ESCAPES = frozenset(".-_/()[]{}+*?|^$" + "\\")

#: Quantifier openers that can make the atom BEFORE them optional: `a?`, `a*`
#: and `a{0,3}` all match without a single `a`. `+` is deliberately absent
#: because it requires at least one, so a run ending at `+` keeps its last
#: character.
_OPTIONAL_QUANTIFIER_OPENERS = frozenset("?*{")

#: Characters Python's IGNORECASE table equates with a NON-ASCII character whose
#: `str.lower()` is not itself: `(?i)s` matches U+017F LATIN SMALL LETTER LONG S,
#: and `(?i)i` matches U+0130 and U+0131. Enumerated over U+0080..U+24FF against
#: every ASCII letter, these are the only two. A literal carrying one is not
#: provable under an in-effect `(?i)`, because the lowered text would not contain
#: it -- which is the rejection direction, so it must be excluded rather than
#: noted.
_FOLD_UNSAFE = "is"

#: Stack bound for nested alternation. `(((( ... ))))` 2,000 deep is a legal
#: 4,000-character pattern, and a register is data that consumers write, so an
#: unbounded walk would raise RecursionError -- while the contract below is that
#: no input raises. Past the bound the answer is `None`, the no-claim direction.
#: This is NOT what terminates the recursion; see `_prove_literals`.
_MAX_ALTERNATION_DEPTH = 32

#: One leading GLOBAL flag group. Only `i`, `m` and `s`: `(?x)` must never be
#: stripped, because VERBOSE changes what a literal IS -- unescaped whitespace
#: and `#` comments stop being characters -- so a run read under it would be
#: wrong rather than merely weak.
_INLINE_FLAGS_RE = re.compile(r"\(\?[ims]+\)")


def _scan_unescaped(pattern: str) -> Iterator[tuple[int, str, int, bool]]:
    """Yield `(index, char, depth, in_class)` for every UNESCAPED character.

    ONE walk behind both the wrapper balance check and the alternation split, so
    the two cannot drift on what a `|` inside `[...]` means. `depth` is the group
    nesting OUTSIDE the yielded character, so the `)` closing a group opened at
    top level is yielded with `depth == 0`.

    A `]` in the FIRST body position is a literal member of the class rather than
    its terminator, so `[]]` is the class containing `]`. Reading that `]` as the
    terminator would end the class early and leave a stray `]` at top level,
    which could mis-locate the group boundary the balance check trusts.
    """
    depth = 0
    in_class = False
    body_start = -1
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            # The escaped character can open or close nothing, so the pair is
            # skipped whole. A TRAILING backslash steps past the end, which the
            # loop condition absorbs: `a\` must not raise.
            index += 2
            continue
        if in_class:
            yield index, char, depth, True
            if char == "]" and index > body_start:
                in_class = False
        elif char == "[":
            in_class = True
            body_start = index + 2 if pattern[index + 1:index + 2] == "^" else index + 1
            yield index, char, depth, False
        elif char == "(":
            yield index, char, depth, False
            depth += 1
        elif char == ")":
            # Floored at zero so an unbalanced `)` cannot drive the depth
            # negative and make a later top-level `|` invisible to the split.
            depth = max(0, depth - 1)
            yield index, char, depth, False
        else:
            yield index, char, depth, False
        index += 1


def _strip_inline_flags(pattern: str) -> tuple[str, bool]:
    """Remove ONE leading flag group, reporting whether `i` was among its letters.

    The flag itself is not a run character, so leaving it in place would end
    every run at the `(` and make every case-insensitive pattern unprovable. The
    `i` has to travel with the stripped text rather than be forgotten: it is what
    decides whether the run may carry an `i` or an `s`.
    """
    match = _INLINE_FLAGS_RE.match(pattern)
    if match is None:
        return pattern, False
    return pattern[match.end():], "i" in match.group(0)


def _strip_full_wrapper(pattern: str) -> str:
    """Remove ONE group enclosing the WHOLE pattern, else return it unchanged.

    Only a plain `(...)` or a non-capturing `(?:...)`, because those are the only
    wrappers that leave the match SET unchanged. `(?=...)` and `(?!...)` are not
    stripped -- the negative form would invert the requirement outright -- and
    neither are `(?<=...)`, `(?P<n>...)` or `(?i:...)`, which simply keep the `(`
    that ends a run at once.

    The balance check is what makes this safe rather than merely convenient.
    `(foo)|(bar)` LOOKS wrapped: it opens with `(` and its last character is `)`.
    A naive strip yields `foo)|(bar`, whose second alternative has no literal at
    all, so the whole pattern would be reported unprovable. Here the group opened
    at index 0 closes at index 4 rather than at the end, so nothing is stripped
    and the split sees both alternatives intact.
    """
    if pattern.startswith("(?:"):
        opener = 3
    elif pattern.startswith("(") and not pattern.startswith("(?"):
        opener = 1
    else:
        return pattern
    for index, char, depth, in_class in _scan_unescaped(pattern):
        if char == ")" and depth == 0 and not in_class:
            return pattern[opener:-1] if index == len(pattern) - 1 else pattern
    return pattern  # the `(` never closes: an unbalanced pattern, strip nothing


def _split_alternatives(pattern: str) -> list[str]:
    """Split on depth-0 `|` only, so `a[|]b|c` is TWO alternatives, not three.

    Top-level alternation is the lowest-precedence operator in a regex, so a
    match of the whole is a match of one alternative -- which is what lets the
    caller UNION the alternatives' literals instead of intersecting them.
    """
    bars = [index for index, char, depth, in_class in _scan_unescaped(pattern)
            if char == "|" and depth == 0 and not in_class]
    if not bars:
        return [pattern]
    parts: list[str] = []
    start = 0
    for bar in bars:
        parts.append(pattern[start:bar])
        start = bar + 1
    parts.append(pattern[start:])
    return parts


def _leading_literal_run(alternative: str, fold: bool) -> str:
    """The lowercased characters EVERY match of one alternative must contain.

    Returns `""` when nothing is provable, which the caller reads as "no claim".
    Three conditions end the run, each in the conservative direction: an
    unescaped metacharacter, an escape outside the punctuation whitelist, and a
    NON-ASCII character. The last one is a soundness requirement, not tidiness:
    `str.lower()` is context-dependent outside ASCII -- a Greek capital sigma
    lowercases to one codepoint at the end of a word and a different one inside
    it -- so a non-ASCII literal lowered in isolation need not be a substring of
    the lowered text.

    The last run character is DROPPED when the next pattern character is `?`, `*`
    or `{`, because a quantifier binds the single atom before it and all three
    admit zero of it: `foobar?` matches `fooba`, and `ab{0,3}c` matches `ac`.
    """
    chars: list[str] = []
    index = 0
    while index < len(alternative):
        char = alternative[index]
        if char == "\\":
            escaped = alternative[index + 1:index + 2]
            if escaped not in _LITERAL_ESCAPES:
                break  # a class, an assertion, a backreference, or a bare `\`
            chars.append(escaped)
            index += 2
            continue
        if char in _RUN_ENDERS or not char.isascii():
            break
        chars.append(char)
        index += 1
    if chars and alternative[index:index + 1] in _OPTIONAL_QUANTIFIER_OPENERS:
        chars.pop()
    run = "".join(chars).lower()
    if not fold:
        return run
    # Under an in-effect `(?i)` the run may not carry `i` or `s`, so the LONGEST
    # fold-safe segment of it stands in. Any contiguous piece of a mandatory run
    # is itself mandatory, so this weakens the filter without weakening the
    # proof. Ending the run at the first `i` or `s` instead would answer `o` for
    # `(?i)os\.walk\(` and nothing at all for `(?i)sk_live_`.
    return max(re.split(f"[{_FOLD_UNSAFE}]", run), key=len)


def _prove_literals(pattern: str, depth: int, fold: bool) -> frozenset[str] | None:
    """One level of the public extractor, carrying the fold state down the walk.

    The recursion is what makes `(foo)|(bar)` provable. `_strip_full_wrapper`
    refuses to strip a group that does not enclose the whole pattern, so those
    alternatives arrive here still wrapped and each is normalised in its own
    right. At most ONE wrapper is stripped per level, so `((a|b))` costs two
    levels instead of being read as the single alternative `(a|b)`, whose run
    would stop at the `(` and report nothing provable.

    Every recursive call receives a STRICTLY shorter string -- a strip removes
    characters, and a split removes at least the bar -- so the walk terminates on
    its own. `_MAX_ALTERNATION_DEPTH` bounds the STACK rather than the walk,
    because a legal 4,000-character pattern can nest 2,000 deep and the contract
    is that no input raises.
    """
    if depth > _MAX_ALTERNATION_DEPTH:
        return None
    stripped, folded = _strip_inline_flags(pattern)
    fold = fold or folded
    stripped = _strip_full_wrapper(stripped)
    alternatives = _split_alternatives(stripped)
    if len(alternatives) == 1 and stripped == pattern:
        run = _leading_literal_run(pattern, fold)
        return frozenset({run}) if run else None
    literals: set[str] = set()
    for alternative in alternatives:
        proved = _prove_literals(alternative, depth + 1, fold)
        if proved is None:
            # ONE alternative with no mandatory literal makes the WHOLE pattern
            # unprovable. A text missing every other alternative's literal can
            # still match through this one, so no member of the set would be
            # decisive and skipping the file would be a false ABSENT.
            return None
        literals |= proved
    return frozenset(literals) if literals else None


def required_literals(pattern: str) -> frozenset[str] | None:
    r"""Literals every match of `pattern` must contain, or None when unprovable.

    The published guarantee, and the only thing a caller may rely on:

        If it returns a set `L`, then `L` is non-empty and for every text `t`, if
        `re.compile(pattern, re.MULTILINE).search(t)` is not `None`, then at
        least one member of `L` is a substring of `t.lower()`.

    So a text containing no member of `L` cannot match, and the regex over it can
    be skipped. `evaluate`'s content branch is the only caller, and this shipped
    one bite ahead of it because the failure an unsound literal causes is the
    INVERTED one -- a wrongly skipped file turns a PRESENT into an ABSENT, a
    false claim of safety.

    Only ONE direction is proved, and that asymmetry is the design. A missing
    literal is decisive. A PRESENT literal proves nothing, and `None` proves
    nothing: both mean "run the regex", so every unproved pattern costs a regex
    pass and can never cost a verdict.

    Lowercasing is sound in the REJECTION direction, which is the only direction
    used. The caller tests membership against `text.lower()`, so folding can only
    ADMIT a file the regex then rejects -- a wasted pass -- and can never reject a
    file the regex would have matched. Two Unicode facts are what make that hold,
    and each costs a rule in `_leading_literal_run`: `str.lower()` is
    context-dependent outside ASCII, so a run stops at the first non-ASCII
    character; and Python's IGNORECASE table equates `i` and `s` with U+0130,
    U+0131 and U+017F, whose `str.lower()` stays outside ASCII, so under an
    in-effect `(?i)` the literal may not carry either letter.

    The escape whitelist is punctuation only -- `. - _ / ( ) [ ] { } + * ? | ^ $
    \` -- so `\.` contributes `.` and `os\.walk\(` proves `os.walk(`. Every
    alphanumeric escape (`\b`, `\w`, `\d`, `\s`, `\1`) ENDS the run, because it
    denotes a class, an assertion or a backreference rather than a character that
    must appear.

    Returns `None` or a NON-EMPTY frozenset, never `frozenset()`: an empty set
    would read as "no literal is required", which is what a caller checking
    `if literals:` would treat as "skip nothing" while a caller checking
    `if literals is not None:` would treat as "skip everything".
    """
    return _prove_literals(pattern, 0, False)
