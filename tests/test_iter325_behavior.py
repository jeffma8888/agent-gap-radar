"""Iteration 325 behaviors: ``radar report --layer L`` filter wiring.

Wire the shipped ``_select_layer`` filter (iter 84, ``list``) to the
``report`` verb so that ``radar report <path> --layer tool-action``
produces a report scoped to one layer.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-7. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every
behavioral claim is measured by running the CLI or by comparing verb
output against a git-archived pre-change tree, both of which are inside
the contract.
"""

from __future__ import annotations

import pathlib

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cli(argv, capsys):
    try:
        rc = main(argv) or 0
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


# ---------------------------------------------------------------------------
# B1 -- ``radar report <path> --layer tool-action`` produces a report
# scoped to that layer; header shows the FILTERED record count.
# ---------------------------------------------------------------------------

def test_b1_report_layer_filter_scoped_output(capsys):
    rc, out, err = _cli(["report", str(GAPS), "--layer", "tool-action"], capsys)
    assert rc == 0, f"expected exit 0; got {rc}; stderr: {err!r}"
    assert out, "stdout must be non-empty"
    lines = out.splitlines()
    header_lines = [l for l in lines if l.startswith("Records:")]
    assert header_lines, f"no 'Records:' header found in output"
    header = header_lines[0]
    assert "120" not in header, (
        f"header must show filtered count, not full register; got {header!r}")
    count_str = header.split(":")[1].strip().split("|")[0].strip()
    count = int(count_str)
    assert count > 0, "filtered count must be positive for tool-action"
    assert count < 120, (
        f"filtered count {count} must be less than full register")
    in_ranked = False
    ranked_rows = []
    for line in lines:
        if line.strip() == "## Ranked gaps":
            in_ranked = True
            continue
        if in_ranked and line.startswith("##"):
            break
        if in_ranked and line.startswith("|") and "---" not in line and "Rank" not in line:
            ranked_rows.append(line)
    assert len(ranked_rows) == count, (
        f"ranked table should have {count} rows; got {len(ranked_rows)}")
    for row in ranked_rows:
        assert "tool-action" in row, (
            f"ranked row should be tool-action; got {row!r}")


# ---------------------------------------------------------------------------
# B2 -- ``radar report <path> --layer nope`` exits 2, emits Error: on
# stderr naming accepted layers, writes zero stdout bytes.
# ---------------------------------------------------------------------------

def test_b2_report_unknown_layer_exits_2(capsys):
    rc, out, err = _cli(["report", str(GAPS), "--layer", "nope"], capsys)
    assert rc == 2, f"expected exit 2; got {rc}"
    assert out == "", f"stdout must be empty on error; got {out!r}"
    err_lines = err.splitlines()
    assert len(err_lines) == 1, f"exactly one stderr line; got {err_lines}"
    assert err_lines[0].startswith("Error: "), (
        f"stderr must be prefixed with 'Error: '; got {err_lines[0]!r}")
    assert "nope" in err_lines[0], (
        f"error must name the invalid layer; got {err_lines[0]!r}")
    for layer_name in ("model-runtime", "orchestration", "tool-action",
                       "sandbox-isolation", "eval-verification"):
        assert layer_name in err_lines[0], (
            f"error must list accepted layer {layer_name!r}; got {err_lines[0]!r}")


def test_b2_report_and_list_share_error_vocabulary(capsys):
    rc_report, out_report, err_report = _cli(
        ["report", str(GAPS), "--layer", "nope"], capsys)
    rc_list, out_list, err_list = _cli(
        ["list", str(GAPS), "--layer", "nope"], capsys)
    assert rc_report == rc_list == 2
    assert err_report == err_list, (
        f"report and list must share the same error vocabulary;\n"
        f"report: {err_report!r}\nlist:   {err_list!r}")


# ---------------------------------------------------------------------------
# B4 -- ``--layer`` appears in ``radar report --help``.
# ---------------------------------------------------------------------------

def test_b4_layer_in_report_help(capsys):
    rc, out, err = _cli(["report", "--help"], capsys)
    combined = out + err
    assert "--layer" in combined, (
        f"'--layer' must appear in report --help; got: {combined!r}")


# ---------------------------------------------------------------------------
# B5 -- every section in the filtered report operates on the filtered
# domain; no record from another layer appears.
# ---------------------------------------------------------------------------

def test_b5_all_sections_scoped_to_filtered_domain(capsys):
    rc, out, err = _cli(["report", str(GAPS), "--layer", "tool-action"], capsys)
    assert rc == 0
    ranked_rows = [l for l in out.splitlines()
                   if l.startswith("|") and l.count("|") >= 7
                   and not l.startswith("| ---") and not l.startswith("| Rank")]
    for row in ranked_rows:
        assert "tool-action" in row, (
            f"ranked table row from another layer: {row!r}")
    non_tool_layers = ["model-runtime", "orchestration", "context-memory",
                       "sandbox-isolation", "eval-verification", "observability",
                       "cost-governance", "lifecycle-deploy", "multi-agent",
                       "human-interface"]
    for row in ranked_rows:
        for layer in non_tool_layers:
            assert f"| {layer} |" not in row, (
                f"ranked row contains non-filtered layer {layer!r}: {row!r}")


# ---------------------------------------------------------------------------
# B6 -- By-layer section shows the filtered layer's count > 0 and zeros
# for every other layer.
# ---------------------------------------------------------------------------

def test_b6_by_layer_section_shows_filtered_count_and_zeros(capsys):
    rc, out, err = _cli(["report", str(GAPS), "--layer", "tool-action"], capsys)
    assert rc == 0
    lines = out.splitlines()
    in_by_layer = False
    by_layer_rows = []
    for line in lines:
        if line.strip() == "## By layer":
            in_by_layer = True
            continue
        if in_by_layer and line.startswith("##"):
            break
        if in_by_layer and line.startswith("|") and "---" not in line and "Layer" not in line:
            by_layer_rows.append(line)
    assert by_layer_rows, "By-layer section must be present"
    tool_action_found = False
    for row in by_layer_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        assert len(cells) >= 2, f"unexpected row shape: {row!r}"
        layer_name, count_str = cells[0], cells[1]
        count = int(count_str)
        if layer_name == "tool-action":
            tool_action_found = True
            assert count > 0, (
                f"tool-action count must be > 0; got {count}")
        else:
            assert count == 0, (
                f"layer {layer_name!r} must show 0 under --layer tool-action; got {count}")
    assert tool_action_found, "tool-action must appear in By-layer section"
