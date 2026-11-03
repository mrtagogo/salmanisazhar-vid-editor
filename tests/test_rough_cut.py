"""The approval gate, and the arithmetic behind the cut.

Run from the engine root:

    python -m tests.test_rough_cut

The gate is the point of the whole analysis milestone: everything stops at a
human decision. A cutting stage that could be talked into running without one
would make the checkpoint decorative, so most of this file is about refusing.

The other half is subtler. Approving means editing statuses in the EDL — each
'review' becomes 'auto' or 'blocked'. The `plans` block stored in that file
was computed BEFORE anyone edited it, so after approval it describes a
decision nobody made. The cut must be built from the statuses as they stand.
"""

from __future__ import annotations

import sys

from scripts.lib.config import cutting_profile, load_config
from scripts.stages.s04_edl import STATUS_AUTO, STATUS_BLOCKED, STATUS_REVIEW, _build_plan
from scripts.stages.s08_rough_cut import ApprovalError, _filtergraph, _require_approval

_failures: list[str] = []
_checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _checks
    _checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
        _failures.append(label)


def edl(status: str, *, required: bool = True, reviews: int = 0) -> dict:
    return {
        "approval": {"required": required, "status": status},
        "proposals": [
            {"id": f"r{i}", "status": STATUS_REVIEW, "start": 0, "end": 1, "action": "cut"}
            for i in range(reviews)
        ],
    }


def refused(doc: dict) -> bool:
    try:
        _require_approval(doc, "edl.json")
    except ApprovalError:
        return True
    return False


def proposal(pid: str, start: float, end: float, status: str, action: str = "cut") -> dict:
    return {"id": pid, "start": start, "end": end, "status": status, "action": action}


def main() -> int:
    print("The approval gate")
    check("a pending EDL is refused", refused(edl("pending", reviews=3)))
    check("an EDL with no status is refused", refused(edl(None)))
    check("'approved-ish' is not approved", refused(edl("Approved ")))
    check("an approved EDL passes", not refused(edl("approved")))
    check("the gate can be turned off in config, explicitly",
          not refused(edl("pending", required=False)))

    try:
        _require_approval(edl("pending", reviews=4), "projects/x/data/04-edl.json")
        message = ""
    except ApprovalError as exc:
        message = str(exc)
    check("the refusal names the file", "04-edl.json" in message)
    check("the refusal counts what is still open", "4 proposal(s)" in message, message[:80])
    check("the refusal says how to approve", "approvedBy" in message)

    print("\nKeep-ranges come from the statuses, not the stored plan")
    config = load_config()
    profile = cutting_profile(config)
    proposals = [
        proposal("p1", 2.0, 3.0, STATUS_AUTO),
        proposal("p2", 5.0, 6.0, STATUS_REVIEW),    # a human left this undecided
        proposal("p3", 8.0, 9.0, STATUS_BLOCKED),   # a human refused this one
    ]
    plan = _build_plan(proposals, 10.0, include_review=False, profile=profile)
    applied = plan["acceptedProposalIds"]
    check("an approved cut is applied", "p1" in applied)
    check("an undecided cut is NOT applied", "p2" not in applied, str(applied))
    check("a refused cut is NOT applied", "p3" not in applied, str(applied))
    check("one removal leaves two kept ranges", len(plan["keepRanges"]) == 2,
          str(plan["keepRanges"]))
    check("the removal is the right length", abs(plan["removedSeconds"] - 1.0) < 1e-6)
    check("the result duration adds up",
          abs(plan["resultDurationSeconds"] - 9.0) < 1e-6)

    # Everything blocked: the cut must be the whole recording, not nothing.
    none_applied = _build_plan(
        [proposal("p1", 2.0, 3.0, STATUS_BLOCKED)], 10.0, include_review=False, profile=profile
    )
    check("with everything refused, the whole recording is kept",
          len(none_applied["keepRanges"]) == 1
          and abs(none_applied["keepRanges"][0]["end"] - 10.0) < 1e-6)

    print("\nShort kept segments are warned about, not silently shipped")
    glitchy = _build_plan(
        [proposal("a", 1.0, 2.0, STATUS_AUTO), proposal("b", 2.2, 4.0, STATUS_AUTO)],
        10.0, include_review=False, profile=profile,
    )
    check("a 0.2s survivor raises a warning", bool(glitchy["warnings"]),
          str(glitchy["warnings"]))

    print("\nThe filtergraph")
    graph = _filtergraph([{"start": 0.0, "end": 2.0}, {"start": 5.0, "end": 7.5}])
    check("one video trim per range", graph.count("trim=start=") == 4,
          f"got {graph.count('trim=start=')} (video+audio for 2 ranges)")
    check("audio is trimmed with the video", graph.count("atrim=start=") == 2)
    check("timestamps are reset on every piece", graph.count("setpts=PTS-STARTPTS") == 4)
    check("the pieces are concatenated in order", "[v0][a0][v1][a1]concat=n=2" in graph, graph[-60:])
    check("the outputs are named", "[vout][aout]" in graph)
    single = _filtergraph([{"start": 1.0, "end": 2.0}])
    check("a single range still concatenates cleanly", "concat=n=1" in single)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
