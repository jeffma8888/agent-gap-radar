"""Reconstruct the exact bytes an appended JSON key or list item contributes.

Two committed pins measure the prd document as ONE number -- `test_iter68_behavior`'s
`PRE_ITERATION_BYTES` arithmetic and `test_iter217_behavior`'s pre-change sha256 -- and
both are deliberately captured from an implementation that no longer runs, so neither may
be re-pinned from the working tree: a rendering regression must not be able to re-baseline
itself. When an iteration legitimately APPENDS to that document, the honest update is to
keep the historical witness and account for the growth as a MEASURED term, which is what
iteration 92 did for `sourceGap.status` and iteration 221 does for
`sourceGap.check.closure` and US-002's closure criterion.

The reconstruction needs no unit test of its own, because every call site asserts
`out.count(fragment) == 1` BEFORE using it: a fragment built with the wrong indent, the
wrong separators or the wrong value occurs ZERO times in the emitted bytes and reds the
pin it was meant to satisfy. That premise is the two-sided proof, and it is measured
against the real document rather than a fixture of one.

`render.json_document` is the single emitter (`indent=2`, `sort_keys=False`, default
separators), so these helpers hard-code that one shape rather than accepting options for
renderings this repo does not have.
"""

from __future__ import annotations

import json

_INDENT = 2


def _reindent(rendered: str, columns: int) -> str:
    """Shift every line but the first right by `columns`, as nesting does."""
    head, *rest = rendered.split("\n")
    pad = " " * columns
    return "\n".join([head, *(pad + line for line in rest)])


def appended_key_fragment(key: str, container: dict, columns: int) -> str:
    """The bytes `key` adds to an already non-empty object whose members sit at `columns`.

    The leading comma belongs to the fragment: appending to a non-empty object also
    punctuates the key that used to be last, and a size claim that ignored that byte
    would be off by one per append.
    """
    value = _reindent(json.dumps(container[key], indent=_INDENT), columns)
    return f',\n{" " * columns}"{key}": {value}'


def appended_item_fragment(item: object, columns: int) -> str:
    """The bytes a scalar list item adds to an already non-empty array at `columns`."""
    return f',\n{" " * columns}{json.dumps(item)}'
