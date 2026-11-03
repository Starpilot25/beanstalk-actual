"""
Compare the real survey (Google Form export) with the AI personas.

    py personas/compare.py real.csv

real.csv = Google Sheets -> File -> Download -> CSV of the form responses. Columns are found by their question
wording, so the export can be used as is. Writes personas/out/compare.md (numbers for FEEDBACK.md).
"""
import csv
import statistics as st
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
SCORES = [("looks_like_me", "look like you"), ("rings_true", "ring true"), ("professional", "look professional")]
TEXTS = [("looks_like_me_why", None), ("not_good", "isn't good"), ("liked", "anything you liked")]


def find(header, words):
    for i, h in enumerate(header):
        if words.lower() in h.lower().replace("’", "'"):
            return i
    return None


def load_real(path):
    rows = list(csv.reader(open(path, encoding="utf-8-sig")))
    head, data = rows[0], rows[1:]
    out = []
    for r in data:
        rec = {}
        for key, words in SCORES:
            i = find(head, words)
            rec[key] = int(r[i][0]) if i is not None and r[i][:1].isdigit() else None
        i = find(head, "isn't good")
        rec["not_good"] = r[i] if i is not None else ""
        out.append(rec)
    return out


def load_ai():
    out = []
    for r in csv.DictReader(open(OUT / "responses.csv", encoding="utf-8")):
        out.append({k: (int(r[k]) if r[k].isdigit() else None) for k, _ in SCORES} | {"not_good": r["not_good"]})
    return out


def summary(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return "—"
    dist = " ".join(f"{s}:{v.count(s)}" for s in range(1, 6))
    sd = st.pstdev(v)
    return f"mean {st.mean(v):.1f}, median {st.median(v):g}, spread (sd) {sd:.1f} — [{dist}]"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    real, ai = load_real(sys.argv[1]), load_ai()
    lines = ["# Real vs AI personas: the numbers", "", f"Real: {len(real)} responses. AI: {len(ai)} personas.", "",
             "| Question | Real people | AI personas |", "|---|---|---|"]
    for key, words in SCORES:
        lines.append(f"| {words.capitalize()}? | {summary([r[key] for r in real])} | {summary([r[key] for r in ai])} |")
    for label, group in (("Real", real), ("AI", ai)):
        lens = [len(r["not_good"].split()) for r in group if r["not_good"]]
        if lens:
            lines.append(f"\n{label}: \"what isn't good\" averages {st.mean(lens):.0f} words.")
    lines += ["", "## \"What isn't good\", side by side", "", "**Real**", ""]
    lines += [f"- {r['not_good']}" for r in real if r["not_good"]]
    lines += ["", "**AI**", ""] + [f"- {r['not_good']}" for r in ai if r["not_good"]]
    (OUT / "compare.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8]))
    print("\nWrote personas/out/compare.md")


if __name__ == "__main__":
    main()
