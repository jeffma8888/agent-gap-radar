"""Iteration 417 behaviors: one suite-wide autouse socket tripwire in `tests/conftest.py`
replaces the per-module socket-only copies in the iter72/73/74/85 modules.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors; nothing here reads `src/`, the engineer's or reviewer's
notes, or a diff. The conftest and the sibling TEST modules are read as text and AST,
because they are the object under test this iteration.

Structural notes, so this file cannot lie later:

* **This module defines NO fixture of its own** (behavior 2), so every tripwire hit below
  is the conftest firing, not a local copy. A node pins that absence.
* **The tripwire assertions are the red-at-pre-feature oracle**: without the conftest,
  `socket.socket()` builds a real socket, `getaddrinfo("localhost", 80)` resolves, and
  `create_connection(("127.0.0.1", 9))` raises a plain `OSError`, none of which is the
  `AssertionError`-typed tripwire with the pinned message.
* **Restoration is measured in a child interpreter** that runs pytest in-process over a
  COPY of the conftest under `tmp_path` and then checks that `socket.socket` is the
  original object again. It writes nothing into the live `tests/` dir.
* **Deleted test names are assembled from fragments**, so a text census of `tests/` never
  finds this module as its own hit, and every "finds nothing" census has a control.
* **No commit sha, line number or `file:line` locator is pinned, and no wall-clock bound.**
* **No absolute machine path and no personal identifier appears here.**
"""

from __future__ import annotations

import ast
import os
import pathlib
import socket
import subprocess
import sys
import textwrap

import pytest

TESTS = pathlib.Path(__file__).resolve().parent
CONFTEST = TESTS / "conftest.py"
MESSAGE = "network access attempted during test"
ENTRY_POINTS = ("socket", "create_connection", "getaddrinfo")
SOCKET_ONLY_MODULES = ("72", "73", "74", "85")
SUBPROCESS_TRIPWIRE_MODULES = ("248", "79")
PATCH_SOCKET = "monkeypatch.setattr(" + "socket"


def _module(nn: str) -> pathlib.Path:
    return TESTS / f"test_iter{nn}_behavior.py"


def _tree(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=path.name)


def _is_fixture_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute):
        return target.attr == "fixture"
    return isinstance(target, ast.Name) and target.id == "fixture"


def _is_autouse(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    for kw in node.keywords:
        if kw.arg == "autouse" and isinstance(kw.value, ast.Constant):
            return kw.value.value is True
    return False


def _fixture_defs(tree: ast.Module) -> list[ast.FunctionDef]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and any(_is_fixture_decorator(d) for d in n.decorator_list)
    ]


def _autouse_fixtures(tree: ast.Module) -> list[ast.FunctionDef]:
    return [f for f in _fixture_defs(tree) if any(_is_autouse(d) for d in f.decorator_list)]


def _test_names(tree: ast.Module) -> set[str]:
    return {
        n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    }


# --- behavior 1 + 2: the conftest fires in a fixture-less module --------------------------


def test_b1_conftest_exists_and_parses() -> None:
    assert CONFTEST.is_file(), "tests/conftest.py must exist"
    _tree(CONFTEST)


def test_b2_this_module_defines_no_fixture_of_its_own() -> None:
    own = _tree(pathlib.Path(__file__))
    assert _fixture_defs(own) == [], "behavior 2: the module must rely on the conftest only"
    # Control: the detector does see a fixture where one exists.
    assert _fixture_defs(_tree(CONFTEST)), "premise: the conftest defines a fixture"


def test_b2_socket_socket_raises_the_tripwire() -> None:
    with pytest.raises(AssertionError, match=MESSAGE):
        socket.socket()


def test_b2_socket_socket_with_family_args_raises_the_tripwire() -> None:
    with pytest.raises(AssertionError, match=MESSAGE):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_b2_create_connection_raises_the_tripwire_not_a_plain_oserror() -> None:
    with pytest.raises(AssertionError, match=MESSAGE) as info:
        socket.create_connection(("127.0.0.1", 9))
    assert not isinstance(info.value, OSError), "a breach must not be swallowable as OSError"


def test_b2_create_connection_with_timeout_kwarg_raises_the_tripwire() -> None:
    with pytest.raises(AssertionError, match=MESSAGE):
        socket.create_connection(("127.0.0.1", 9), timeout=1)


def test_b2_getaddrinfo_raises_the_tripwire() -> None:
    with pytest.raises(AssertionError, match=MESSAGE):
        socket.getaddrinfo("localhost", 80)


def test_b2_a_fresh_import_of_socket_sees_the_tripwire_too() -> None:
    import socket as again  # noqa: PLC0415  (deliberately local)

    with pytest.raises(AssertionError, match=MESSAGE):
        again.getaddrinfo("127.0.0.1", 9)


def test_b1_raised_type_is_the_conftest_assertionerror_subclass() -> None:
    import conftest  # noqa: PLC0415  (tests/ is on sys.path; this is the live conftest)

    exc_types = [
        v
        for v in vars(conftest).values()
        if isinstance(v, type) and issubclass(v, AssertionError) and v is not AssertionError
    ]
    assert exc_types, "behavior 1: the conftest defines an AssertionError subclass"
    for call in (
        lambda: socket.socket(),
        lambda: socket.create_connection(("127.0.0.1", 9)),
        lambda: socket.getaddrinfo("localhost", 80),
    ):
        with pytest.raises(AssertionError) as info:
            call()
        assert type(info.value) is not AssertionError, "must be a SUBCLASS, not bare AssertionError"
        assert isinstance(info.value, tuple(exc_types))
        assert MESSAGE in str(info.value)


# --- behavior 3: registered as autouse, source names all three entry points --------------


def test_b3_the_conftest_autouse_fixture_is_active_for_this_test(request: pytest.FixtureRequest) -> None:
    autouse = _autouse_fixtures(_tree(CONFTEST))
    assert autouse, "behavior 3: the conftest defines an autouse fixture"
    for fixture in autouse:
        assert fixture.name in request.fixturenames, fixture.name


def test_b3_the_autouse_fixture_source_names_all_three_entry_points() -> None:
    source = CONFTEST.read_text(encoding="utf-8")
    autouse = _autouse_fixtures(_tree(CONFTEST))
    assert autouse
    bodies = "\n".join(ast.get_source_segment(source, f) or "" for f in autouse)
    for name in ENTRY_POINTS:
        assert f'"{name}"' in bodies or f"'{name}'" in bodies, name
    assert "monkeypatch" in bodies, "behavior 1: originals are restored via monkeypatch"


def test_b3_the_autouse_fixture_is_function_scoped() -> None:
    for fixture in _autouse_fixtures(_tree(CONFTEST)):
        for deco in fixture.decorator_list:
            if isinstance(deco, ast.Call):
                for kw in deco.keywords:
                    if kw.arg == "scope":
                        assert isinstance(kw.value, ast.Constant) and kw.value.value == "function"


def test_b1_conftest_changes_nothing_else_about_collection() -> None:
    tree = _tree(CONFTEST)
    hooks = [
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("pytest_")
    ]
    assert hooks == [], f"acceptance: no hooks in the conftest, found {hooks}"
    assigned = {
        t.id
        for n in tree.body
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        if isinstance(t, ast.Name)
    }
    assert "pytest_plugins" not in assigned
    assert "collect_ignore" not in assigned and "collect_ignore_glob" not in assigned


# --- behavior 1: originals come back after each test ------------------------------------


def test_b1_originals_are_restored_after_each_test(tmp_path: pathlib.Path) -> None:
    work = tmp_path / "probe"
    work.mkdir()
    (work / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    (work / "test_probe.py").write_text(
        textwrap.dedent(
            f"""
            import socket
            import pytest

            def test_one():
                with pytest.raises(AssertionError, match={MESSAGE!r}):
                    socket.socket()

            def test_two():
                with pytest.raises(AssertionError, match={MESSAGE!r}):
                    socket.getaddrinfo("localhost", 80)
            """
        ),
        encoding="utf-8",
    )
    (work / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    driver = textwrap.dedent(
        """
        import socket, sys
        originals = (socket.socket, socket.create_connection, socket.getaddrinfo)
        import pytest
        rc = pytest.main(["-q", "-p", "no:cacheprovider", "-p", "no:xdist", "test_probe.py"])
        after = (socket.socket, socket.create_connection, socket.getaddrinfo)
        restored = all(a is b for a, b in zip(originals, after))
        print("RESTORED" if restored else "LEAKED")
        sys.exit(int(rc) or (0 if restored else 3))
        """
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST")}
    proc = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout, proc.stdout
    assert proc.stdout.rstrip().endswith("RESTORED"), proc.stdout


# --- behavior 4: the socket-only module copies are gone -----------------------------------


@pytest.mark.parametrize("nn", SOCKET_ONLY_MODULES)
def test_b4_socket_only_modules_no_longer_patch_socket(nn: str) -> None:
    path = _module(nn)
    assert path.is_file(), f"control: {path.name} still exists"
    text = path.read_text(encoding="utf-8")
    assert PATCH_SOCKET not in text, f"{path.name} still patches socket itself"


@pytest.mark.parametrize("nn", SOCKET_ONLY_MODULES)
def test_b4_socket_only_modules_define_no_socket_fixture(nn: str) -> None:
    path = _module(nn)
    source = path.read_text(encoding="utf-8")
    tree = _tree(path)
    for fixture in _fixture_defs(tree):
        body = ast.get_source_segment(source, fixture) or ""
        assert "socket" not in body, (
            f"{path.name}::{fixture.name} still looks like a socket tripwire"
        )
    assert _test_names(tree), f"control: {path.name} still holds tests"


@pytest.mark.parametrize("nn", SOCKET_ONLY_MODULES)
def test_b4_no_unused_import_socket_is_left_behind(nn: str) -> None:
    tree = _tree(_module(nn))
    imports_socket = any(
        isinstance(n, ast.Import) and any(a.name == "socket" and a.asname is None for a in n.names)
        for n in ast.walk(tree)
    )
    if imports_socket:
        used = any(isinstance(n, ast.Name) and n.id == "socket" for n in ast.walk(tree))
        assert used, f"test_iter{nn}: `import socket` is left unused"


def test_b4_the_tripwire_arming_tests_are_deleted() -> None:
    armed = "the_socket_" + "tripwire_is_armed_and_would_fire"
    gone = {
        "72": {"test_b14_" + armed},
        "85": {
            "test_b7_" + armed,
            "test_b7_the_" + "tripwire_fixture_is_autouse_and_patches_all_three_entry_points",
        },
    }
    for nn, names in gone.items():
        present = _test_names(_tree(_module(nn)))
        assert present, f"control: test_iter{nn} still holds tests"
        assert not (names & present), f"test_iter{nn} still defines {sorted(names & present)}"


def test_b4_detector_premise_finds_a_patch_where_one_exists() -> None:
    # Control for the "finds nothing" census: the same probe DOES find the pattern in
    # the modules that keep their own (subprocess-arming) fixture, and in the conftest's
    # fixture body by entry-point name.
    hits = [nn for nn in SUBPROCESS_TRIPWIRE_MODULES if PATCH_SOCKET in _module(nn).read_text("utf-8")]
    assert hits, "premise: the census pattern still matches somewhere"


# --- behavior 5: the subprocess-arming modules keep their own fixtures --------------------


@pytest.mark.parametrize("nn", SUBPROCESS_TRIPWIRE_MODULES)
def test_b5_subprocess_tripwire_modules_keep_their_own_fixture(nn: str) -> None:
    path = _module(nn)
    assert path.is_file()
    source = path.read_text(encoding="utf-8")
    bodies = "\n".join(ast.get_source_segment(source, f) or "" for f in _fixture_defs(_tree(path)))
    assert "subprocess" in bodies, f"{path.name} still arms its module-specific subprocess tripwire"


# --- behavior 6: hygiene of what this iteration adds --------------------------------------


@pytest.mark.parametrize("path", [CONFTEST, pathlib.Path(__file__)], ids=["conftest", "iter417"])
def test_b6_new_files_carry_no_absolute_machine_path(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    for marker in ("/" + "Users/", "/" + "home/", "C:" + "\\"):
        assert marker not in text, f"{path.name} contains {marker!r}"


def test_b6_conftest_imports_nothing_beyond_socket_and_pytest() -> None:
    roots = set()
    for node in ast.walk(_tree(CONFTEST)):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {"__future__", "socket", "pytest"}, roots
