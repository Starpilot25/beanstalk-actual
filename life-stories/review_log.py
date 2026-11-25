"""
Review a life-story log mechanically:  python review_log.py franklin-log.json

Download any story's log from the site (/life/s/<id>/log.json). This checks:
  1. every fact cites a chunk that was actually retrieved for its question;
  2. every story sentence cites at least one chunk;
  3. every name and number in a sentence appears in the chunks that sentence cites (a name or number that doesn't
     can only have come from the model's own training data);
  4. sentences that lean on exactly the same chunks (likely repeats);
  5. the model checker's verdicts and the canary.
"""
import json
import re
import sys

COMMON = set("""He She His Her Him The A An One Another When Then Some Later Years It They Their In On At As While After
And But Once There This That These Those Dr Mr Mrs Miss Sir Many Every Also Even Still Soon Long Today""".split())


def norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def main(path):
    j = json.load(open(path, encoding="utf-8"))
    r, log = j["result"], j["log"]
    person_words = set(r["person"].split()) | {w + "'s" for w in r["person"].split()}
    chunks = {k: v["text"] for k, v in r["chunks"].items()}
    retrieved = {e["qn"]: e["chunk_ids"] for e in log if e["step"] == "retrieve"}
    problems = 0

    bad = [(a["q"], f["chunk"]) for a in r["answers"] for f in a["facts"] if f["chunk"] not in retrieved.get(a["q"], [])]
    print(f"1. Facts citing a chunk not retrieved for their question: {bad or 'none'}")
    problems += len(bad)

    kept = [s for s in r["sentences"] if not s.get("removed")]
    uncited = [s["id"] for s in kept if not s["chunks"]]
    print(f"2. Sentences in the story: {len(kept)}; citing no chunk: {uncited or 'none'}")
    problems += len(uncited)

    print("3. Names and numbers not found in the cited chunks:")
    n = 0
    for s in kept:
        text = norm(" ".join(chunks.get(f"c{c}", "") for c in s["chunks"]))
        toks = re.findall(r"\b(?:[A-Z][a-z'’]+|\d[\d,]*)\b", s["text"])
        miss = [t for t in toks if t not in COMMON and t not in person_words
                and norm(t).split() and norm(t).split()[0] not in text]
        if miss:
            n += 1
            print(f"   {s['id']} (Q{s['q']}): {miss}  —  {s['text']}")
    print("   none" if not n else f"   {n} sentence(s)")
    problems += n

    same = {}
    for s in kept:
        same.setdefault(tuple(sorted(s["chunks"])), []).append(s["id"])
    reps = {",".join(f"c{c}" for c in k): v for k, v in same.items() if len(v) > 1}
    print(f"4. Sentences resting on exactly the same chunks (check for repeats): {reps or 'none'}")

    rv = r["review"]
    print(f"5. Model check: {rv['first_pass_supported']} of {rv['sentences']} supported first time; flagged "
          f"{len(rv['flagged'])}, rewritten {len(rv['repaired'])}, removed {len(rv['removed'])}; facts dropped for a "
          f"quote not in its chunk: {rv['dropped_facts']}")
    if r.get("canary"):
        c = r["canary"]
        print(f"   Canary: {c['question']} -> {c['answer']} ({'passed' if c['passed'] else 'FAILED'})")
    print(f"\n{problems} traceability problem(s).")
    return problems


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1]) else 0)
