"""The numbered decision sheet.

Run from the engine root:

    python -m tests.test_decisions

The presenter asked for this directly: number the cuts, say what each one
removes, recommend, and cut nothing until he answers — so he knows what went
and the edit does not come back a mess.

Two properties matter more than the formatting. A number must keep meaning
the same cut between writing the sheet and answering it, and anything not
named must be KEPT. Both are failures that would look like the tool working.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from scripts.decisions import apply, make, parse_numbers, recommend, why_blocked
from scripts.lib.paths import PROJECTS_DIR

SLUG = "_test-decisions"

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


def proposal(pid: str, start: float, end: float, status: str, kind: str = "pause") -> dict:
    return {
        "id": pid,
        "kind": kind,
        "start": start,
        "end": end,
        "durationSeconds": round(end - start, 3),
        "action": "cut",
        "status": status,
        "reason": "Pause of some length.",
    }


def build_project(generated_at: str = "2026-11-03T00:00:00Z") -> Path:
    root = PROJECTS_DIR / SLUG
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "04-edl.json").write_text(
        json.dumps(
            {
                "generatedAt": generated_at,
                "durationSeconds": 60.0,
                "approval": {"required": True, "status": "pending"},
                "suspectedRegions": [],
                "proposals": [
                    proposal("p-a", 1.0, 4.0, "auto"),
                    proposal("p-b", 10.0, 10.8, "review"),
                    proposal("p-c", 20.0, 23.0, "review"),
                    proposal("p-d", 30.0, 33.0, "blocked"),
                    proposal("p-e", 40.0, 47.0, "review", kind="retake"),
                ],
            }
        ),
        encoding="utf-8",
    )
    (data / "02-transcript.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 4.0,
                        "end": 10.0,
                        "text": "Kalimat pertama di sini",
                        "words": [
                            {"word": "Kalimat", "start": 4.0, "end": 5.0},
                            {"word": "pertama", "start": 5.0, "end": 6.0},
                            {"word": "di", "start": 6.0, "end": 6.4},
                            {"word": "sini", "start": 6.4, "end": 7.0},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


def read_edl() -> dict:
    return json.loads(
        (PROJECTS_DIR / SLUG / "data" / "04-edl.json").read_text(encoding="utf-8")
    )


def refuses(fn) -> bool:
    try:
        fn()
        return False
    except SystemExit:
        return True


def main() -> int:
    print("Reading an answer")
    check("a plain list", parse_numbers("1,3,7") == [1, 3, 7])
    check("a range", parse_numbers("2-5") == [2, 3, 4, 5])
    check("mixed, with spaces", parse_numbers(" 1, 3-5 ,9 ") == [1, 3, 4, 5, 9])
    check("nothing at all", parse_numbers(None) == [] and parse_numbers("") == [])

    print("\nRecommendations")
    check("an approved cut is recommended firmly",
          recommend(proposal("x", 0, 3, "auto")) == ("POTONG", "jelas"))
    check("a refused cut says do not cut",
          recommend(proposal("x", 0, 3, "blocked"))[0] == "JANGAN POTONG")
    check("a long undecided pause leans to cutting",
          recommend(proposal("x", 0, 3, "review"))[0] == "POTONG")
    check("a short undecided pause leans to keeping",
          recommend(proposal("x", 0, 0.9, "review"))[0] == "SIMPAN")
    check("a retake leans to cutting, with the caveat named",
          recommend(proposal("x", 0, 5, "review", kind="retake"))[0] == "POTONG"
          and "disengaja" in recommend(proposal("x", 0, 5, "review", kind="retake"))[1])

    print("\nThe sheet is readable in one language")
    check("unheard speech is explained in Indonesian",
          "transkrip" in why_blocked({"reason": "But 1.44s of this gap is not quiet."}))
    check("a question pause is explained in Indonesian",
          "retoris" in why_blocked({"reason": "Pause follows a question - rhetorical."}))
    check("an unknown reason still says something useful",
          "review-report" in why_blocked({"reason": "something new"}))

    try:
        build_project()
        print("\nWriting the sheet")
        make(SLUG)
        sheet = PROJECTS_DIR / SLUG / "review" / "keputusan-potong.md"
        text = sheet.read_text(encoding="utf-8")
        check("the sheet is written", sheet.is_file())
        check("every proposal is numbered", all(f"## {n}." in text for n in range(1, 6)))
        check("it is ordered by time", text.index("## 1.") < text.index("## 5."))
        check("it says nothing is cut before answering", "sebelum Anda jawab" in text)
        check("the words around a cut are shown", "Kalimat pertama" in text)

        mapping = json.loads(
            (PROJECTS_DIR / SLUG / "data" / "09-decision-numbers.json").read_text(
                encoding="utf-8"
            )
        )
        check("the numbering is recorded", mapping["numbers"]["1"] == "p-a")
        check("it is tied to the EDL it came from",
              mapping["edlGeneratedAt"] == "2026-11-03T00:00:00Z")

        print("\nApplying an answer")
        apply(SLUG, cut=[2, 4], keep=[3], by="tester")
        edl = read_edl()
        status = {p["id"]: p["status"] for p in edl["proposals"]}
        check("a chosen cut is applied", status["p-b"] == "auto", status["p-b"])
        check("a chosen keep is blocked", status["p-c"] == "blocked", status["p-c"])
        check("a cut the engine refuses stays refused", status["p-d"] == "blocked")
        check("an UNNAMED auto cut is kept, not applied", status["p-a"] == "blocked",
              f"got {status['p-a']} — silence must not mean consent")
        check("an unnamed review stays undecided", status["p-e"] == "review")
        check("the EDL is approved", edl["approval"]["status"] == "approved")
        check("who decided is recorded", edl["approval"]["approvedBy"] == "tester")
        check("the sheet is referenced", "keputusan-potong" in edl["approval"]["decisionSheet"])

        print("\nRefusals")
        check("a number that is not on the sheet is refused",
              refuses(lambda: apply(SLUG, cut=[99], keep=[], by="t")))
        check("cut and keep for the same number is refused",
              refuses(lambda: apply(SLUG, cut=[1], keep=[1], by="t")))

        # Regenerate the EDL under the same numbers: the sheet is now stale.
        build_project(generated_at="2026-11-04T00:00:00Z")
        check("a stale sheet is refused",
              refuses(lambda: apply(SLUG, cut=[1], keep=[], by="t")))
    finally:
        shutil.rmtree(PROJECTS_DIR / SLUG, ignore_errors=True)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
