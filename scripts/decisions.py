"""The numbered decision sheet, and applying the answer.

The review report explains the engine's reasoning. This is the other thing a
person actually needs: a plain numbered list of every cut on the table, what
each one removes in his own words, and a recommendation — so the answer can
be "potong 1,3,7" instead of hand-editing JSON.

    python -m scripts.decisions make  --slug kajian-02
    python -m scripts.decisions apply --slug kajian-02 --cut 1,3,5-8 --keep 2,4

The numbering is written down, not recomputed. `make` stores number -> id in
the project, and `apply` reads that file. If the EDL is regenerated the
numbering is stale and `apply` refuses, because "cut number 3" meaning a
different cut than it did yesterday is exactly the kind of quiet error this
sheet exists to prevent.

Anything not named is KEPT. Silence is not consent to cut.

The sheet itself is written in Indonesian: it is the one artefact the
presenter has to read and act on.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .lib.jsonio import read_json, utc_now, write_json
from .lib.paths import PROJECTS_DIR

SHEET = "keputusan-potong.md"
MAP = "09-decision-numbers.json"

OPEN_QUOTE = "“"
CLOSE_QUOTE = "”"
WARNING = "⚠️"


def clock(seconds: float) -> str:
    minutes, rest = divmod(max(0.0, float(seconds)), 60)
    return f"{int(minutes):02d}:{rest:05.2f}"


def quoted(text: str) -> str:
    return f"{OPEN_QUOTE}{text}{CLOSE_QUOTE}"


def words_between(words: list[dict], start: float, end: float) -> str:
    inside = [w["word"].strip() for w in words if w["end"] > start and w["start"] < end]
    return " ".join(inside).strip()


def nearest_before(words: list[dict], t: float) -> str:
    before = [w for w in words if w["end"] <= t + 1e-6]
    return " ".join(w["word"].strip() for w in before[-6:]).strip()


def nearest_after(words: list[dict], t: float) -> str:
    after = [w for w in words if w["start"] >= t - 1e-6]
    return " ".join(w["word"].strip() for w in after[:6]).strip()


def recommend(proposal: dict) -> tuple[str, str]:
    """A recommendation, and how firm it is.

    Review items get a lean rather than a shrug — being told "the engine is
    unsure" for the twelfth time is not useful. The firmness says how much to
    trust the lean.
    """
    if proposal["status"] == "blocked":
        return "JANGAN POTONG", "mesin menolak sendiri"
    if proposal["status"] == "auto":
        return "POTONG", "jelas"

    kind = proposal.get("kind")
    length = float(proposal["durationSeconds"])
    if kind == "retake":
        return "POTONG", "cenderung — kecuali pengulangan ini disengaja"
    if kind == "hesitation":
        return "POTONG", "cenderung"
    if length >= 2.0:
        return "POTONG", "cenderung"
    return "SIMPAN", "cenderung — jeda pendek biasanya ritme bicara"


def describe(proposal: dict, words: list[dict]) -> list[str]:
    """What this cut actually removes, in the speaker's own words."""
    start, end = float(proposal["start"]), float(proposal["end"])
    lines: list[str] = []

    if proposal.get("kind") == "retake":
        evidence = proposal.get("evidence", {})
        lines.append(f"- Dibuang : {quoted(evidence.get('firstTake', ''))}")
        lines.append(f"- Disimpan: {quoted(evidence.get('keptTake', ''))}")
        return lines

    inside = words_between(words, start, end)
    if inside:
        lines.append(f"- Kata yang hilang: {quoted(inside)}")
    else:
        lines.append("- Tidak ada kata di dalamnya (hening / jeda)")

    before = nearest_before(words, start)
    after = nearest_after(words, end)
    if before:
        lines.append(f"- Sebelum: {quoted('...' + before)}")
    if after:
        lines.append(f"- Sesudah: {quoted(after + '...')}")
    return lines


def why_blocked(proposal: dict) -> str:
    """A short Indonesian reason, instead of the engine's English prose.

    The sheet is the one thing the presenter reads and acts on, so it should
    not switch language halfway down. The full English reasoning stays in the
    review report for anyone who wants it.
    """
    reason = proposal.get("reason", "").lower()
    if "not quiet" in reason:
        return (
            "Ada suara di dalam jeda ini yang tidak masuk transkrip. Mesin tidak "
            "memotong ucapan yang tidak bisa ia baca."
        )
    if "follows a question" in reason:
        return "Jeda setelah pertanyaan — diperlakukan sebagai jeda retoris."
    if "protected region" in reason or "recitation" in reason:
        return "Bersinggungan dengan ucapan yang dilindungi (Arab / ayat)."
    if "decision sheet" in reason:
        return "Tidak dipilih di lembar keputusan sebelumnya."
    return "Mesin menolak. Alasan lengkapnya ada di review-report.md."


def make(slug: str) -> int:
    data = PROJECTS_DIR / slug / "data"
    edl = read_json(data / "04-edl.json")
    transcript = read_json(data / "02-transcript.json")
    words = [w for s in transcript.get("segments", []) for w in (s.get("words") or [])]

    proposals = sorted(edl["proposals"], key=lambda p: float(p["start"]))
    duration = float(edl["durationSeconds"])
    suspected = edl.get("suspectedRegions") or []

    numbers: dict[str, str] = {}
    body: list[str] = []
    recommended = 0
    saved = 0.0

    for index, proposal in enumerate(proposals, start=1):
        numbers[str(index)] = proposal["id"]
        verdict, firmness = recommend(proposal)
        if verdict == "POTONG":
            recommended += 1
            saved += float(proposal["durationSeconds"])

        touching = [
            region["id"]
            for region in suspected
            if float(proposal["end"]) > region["start"]
            and float(proposal["start"]) < region["end"]
        ]

        body.append(
            f"## {index}. {clock(float(proposal['start']))} – "
            f"{clock(float(proposal['end']))} · "
            f"{float(proposal['durationSeconds']):.2f}s · {proposal.get('kind', '?')}"
        )
        body.append("")
        body.append(f"**{verdict}** ({firmness})")
        body.append("")
        body.extend(describe(proposal, words))
        if touching:
            body.append(
                f"- {WARNING} **Dengarkan dulu.** Menyentuh {', '.join(touching)}: "
                "ada ucapan di sini yang tidak ada di transkrip, atau mungkin ayat."
            )
        if proposal["status"] == "blocked":
            body.append(f"- Alasan mesin menolak: {why_blocked(proposal)}")
        body.append("")

    header = [
        f"# Keputusan potong — {slug}",
        "",
        f"Durasi asli **{clock(duration)}**. Ada **{len(proposals)}** usulan potong.",
        "",
        f"Kalau semua rekomendasi diikuti: **{recommended} dipotong**, hemat "
        f"**{saved:.1f} detik**, sisa **{clock(duration - saved)}**.",
        "",
        "Balas dengan nomornya saja, misalnya:",
        "",
        "> potong 1,2,5-8 — simpan 3,4",
        "",
        "Yang tidak Anda sebut akan **disimpan**. Tidak ada yang dipotong sebelum "
        "Anda jawab.",
        "",
        "---",
        "",
    ]

    review = PROJECTS_DIR / slug / "review"
    review.mkdir(parents=True, exist_ok=True)
    (review / SHEET).write_text("\n".join(header + body) + "\n", encoding="utf-8")

    write_json(
        data / MAP,
        {
            "schema": "tadabbur-motion/decision-numbers@1",
            "generatedAt": utc_now(),
            # Tied to the EDL it was built from, so a stale sheet cannot be
            # applied to a different set of cuts.
            "edlGeneratedAt": edl.get("generatedAt"),
            "numbers": numbers,
        },
    )

    print(f"sheet   : {review / SHEET}")
    print(f"numbers : {len(numbers)} proposal(s); recommended to cut: {recommended}")
    return 0


def parse_numbers(text: str | None) -> list[int]:
    """Accepts '1,3,5-8'."""
    out: list[int] = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            out.extend(range(int(low), int(high) + 1))
        else:
            out.append(int(part))
    return out


def apply(slug: str, cut: list[int], keep: list[int], by: str) -> int:
    data = PROJECTS_DIR / slug / "data"
    edl_path = data / "04-edl.json"
    edl = read_json(edl_path)
    mapping = read_json(data / MAP)

    if mapping.get("edlGeneratedAt") != edl.get("generatedAt"):
        raise SystemExit(
            "The numbering is stale: the EDL has been regenerated since this sheet "
            "was made, so a number no longer means the same cut.\n"
            f"  Run: python -m scripts.decisions make --slug {slug}"
        )

    both = sorted(set(cut) & set(keep))
    if both:
        raise SystemExit(f"Listed as both cut and keep: {both}")

    numbers: dict[str, Any] = mapping["numbers"]
    unknown = [n for n in cut + keep if str(n) not in numbers]
    if unknown:
        raise SystemExit(f"No such number(s): {unknown}. The sheet has 1..{len(numbers)}.")

    by_id = {p["id"]: p for p in edl["proposals"]}
    decided: list[str] = []

    for n in cut:
        proposal = by_id[numbers[str(n)]]
        if proposal["status"] == "blocked":
            print(
                f"  {n} ({proposal['id']}): the engine refuses this one; left alone.",
                file=sys.stderr,
            )
            continue
        proposal["status"] = "auto"
        decided.append(f"cut {n}")

    for n in keep:
        by_id[numbers[str(n)]]["status"] = "blocked"
        decided.append(f"keep {n}")

    # Anything not named is kept. Silence is not consent to cut.
    named = {numbers[str(n)] for n in cut + keep}
    for proposal in edl["proposals"]:
        if proposal["id"] not in named and proposal["status"] == "auto":
            proposal["status"] = "blocked"
            proposal["reason"] = (
                proposal["reason"].rstrip()
                + " Not chosen on the decision sheet, so it is kept."
            )

    edl["approval"].update(
        {
            "status": "approved",
            "approvedBy": by,
            "approvedAt": utc_now(),
            "decisionSheet": str(PROJECTS_DIR / slug / "review" / SHEET),
        }
    )
    write_json(edl_path, edl)

    will_cut = sum(1 for p in edl["proposals"] if p["status"] == "auto")
    print(f"approved: {', '.join(decided) or 'nothing named'}")
    print(f"will cut: {will_cut} proposal(s)")
    print(f"next    : python -m scripts.run_analysis --slug {slug} --only cut --input ...")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decisions")
    sub = parser.add_subparsers(dest="command", required=True)

    maker = sub.add_parser("make", help="Write the numbered sheet.")
    maker.add_argument("--slug", required=True)

    applier = sub.add_parser("apply", help="Apply an answer and approve the EDL.")
    applier.add_argument("--slug", required=True)
    applier.add_argument("--cut", help="Numbers to cut, e.g. 1,3,5-8")
    applier.add_argument("--keep", help="Numbers to keep.")
    applier.add_argument("--by", default="presenter", help="Who decided.")

    args = parser.parse_args(argv)
    if args.command == "make":
        return make(args.slug)
    return apply(args.slug, parse_numbers(args.cut), parse_numbers(args.keep), args.by)


if __name__ == "__main__":
    raise SystemExit(main())
