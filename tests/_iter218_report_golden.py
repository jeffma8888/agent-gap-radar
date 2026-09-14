"""Pre-change document digests, taken at HEAD `31e5864` BEFORE iteration 218's rename.

Iteration 218 privatised eight `scoring` census helpers, so its whole oracle is that no
rendered byte moved. That equivalence cannot be measured after the fact: once the rename
is on disk, re-rendering only compares the new tree with itself. So the pre-change bytes
are pinned here as a length plus a sha256, recorded while the old names were still live.

Digests rather than the 113 KB of documents themselves, because this repo's stated
convention (iteration 111) is that byte-identity is asserted as determinism plus
cross-route, not as a committed golden blob that buys suite time it does not need. Length
AND hash together still fail loudly: the length localises drift, and the hash catches a
same-length edit that a length alone would wave through.

Each entry is keyed by the argv the document came from, run against the tracked `gaps/`
register. All five exited 0 with empty stderr.
"""

from __future__ import annotations

#: argv tail -> (byte length, sha256 hexdigest) of stdout at HEAD `31e5864`.
PRECHANGE_DOCUMENTS: dict[tuple[str, ...], tuple[int, str]] = {
    ("report", "gaps"): (
        39022, "be4bd4e983356c8b705e3e7c026ca2bc713912c0ac89ad7fe0c1d5587be0165f"),
    ("list", "gaps"): (
        17446, "06906c37e424382884cf2890fa7b57fc101b7eca545a92dcba415cb15f7b2f88"),
    ("list", "gaps", "--json"): (
        50218, "0a6abac448d375df019b45f6af1a9770998a27d445c2d43d565903a776374468"),
    ("validate", "gaps"): (
        29, "5320bce7a70985f99078db703925a635926e4f1fff9dfe908cd5e57b6b930720"),
    ("scan", "gaps"): (
        6025, "8cf1f95984524fa39202aaa46f196a10e8b4376fa8de0c89fcce3a9b5c264a07"),
}
