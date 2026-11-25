# Log review: Benjamin Franklin life story

**Run reviewed:** story `gH-XRIZjUIMp`, Nov 25 2026, made on the live site in 143 s
([story](https://beanstalk.autosignusa.com/life/s/gH-XRIZjUIMp) ·
[log page](https://beanstalk.autosignusa.com/life/s/gH-XRIZjUIMp/log)). The files are in this folder:
[`franklin-story.md`](franklin-story.md) and [`franklin-log.json`](franklin-log.json).

**Corpus:** five Project Gutenberg books, about **1,398 pages** in 4,534 chunks:

| Book | Pages | Chunks |
|---|---|---|
| Franklin, *Autobiography* (#20203) | ≈186 | 561 |
| Morse, *Benjamin Franklin* (1889) (#21348) | ≈263 | 884 |
| *The Life of Benjamin Franklin, Illustrated by Tales, Sketches, and Anecdotes* (#38469) | ≈111 | 286 |
| Bruce, *Benjamin Franklin, Self-Revealed*, vol. 1 (1917) (#36896) | ≈414 | 1,355 |
| Bruce, *Benjamin Franklin, Self-Revealed*, vol. 2 (1917) (#36897) | ≈424 | 1,448 |

Pages are estimated at 1,800 characters each, since plain-text books have no page numbers.

**What the log holds:** 51 entries:

- 21 searches: the 20 questions and the canary, each with the 8 chunk IDs it retrieved and their scores.
- 20 answers plus 1 canary answer.
- 1 story-writing call.
- 8 checking calls.

Every model call is logged with the full prompt sent and the reply received. The model calls used 66,236 tokens in
and 28,474 out on gpt-5-mini, about $0.07.

## How I reviewed it

1. **Mechanically**, with [`review_log.py`](review_log.py), which anyone can rerun on any downloaded log:
   - Every fact must cite a chunk that was retrieved for its own question.
   - Every sentence must cite a chunk.
   - Every name and number in a sentence must appear in the chunks it cites. A name or number that doesn't can only
     have come from the model's training.
   - To make sure the check works, I planted "1707" and "He loved Paris" in a copy of the log. It flagged both.
2. **By the app's own check.** Each sentence was sent back to the model with the text of its cited chunks, and the
   model judged whether the chunks support it.
3. **By hand.** I looked up the riskiest 17 claims (dates, numbers, names and places) in their chunks.

## Findings

### Every sentence traces to a chunk ID: 59 of 59

- The review script finds no traceability problems:
  - No fact cites a chunk that wasn't retrieved for its question.
  - No sentence lacks a citation.
  - No name or number is missing from the cited chunks.
- The app's checker passed all 59 sentences the first time, so nothing had to be rewritten or removed.
- By hand, all 17 claims I looked up are in their chunks. Some examples:

| Story says | Chunk says |
|---|---|
| Born in Boston on January 17, 1706 (c1456) | "born in Boston, New England, on the seventeenth of January, 1706. He was the youngest son in a family of seventeen children" |
| Some sources give January 6, old style, Milk Street (c43) | the chunk gives January 6, 1706 (old style) and a house on Milk Street |
| Josiah migrated to Boston, Massachusetts (c587) | "about 1682 Josiah Franklin… migrated to Boston, Massachusetts" |
| Married September 1, 1730 (c226) | "I took her to wife, September 1st, 1730" |
| Died April 17, 1790 (c1655) | "On the 17th of April, 1790, about eleven o'clock at night, Dr. Franklin quietly expired" |
| "Philadelphia has taken Howe" (c3115) | "'No,' he said, 'Philadelphia has taken Howe'" |
| Lamp with three wicks, light of six candles (c4181) | the chunk says the same |

### Anything from the model's training data? None in the final story

The model does know Franklin well, and the log shows two places where it reached past the snippets. **Both were
caught before the story was written**, because each fact's quote must appear word for word in the chunk it cites:

- **Q3:** "His father resolved he should serve the church…" The quote mixed the chunk's words with the model's own
  ("as the tithe of his sons… and so sent him to the grammar school").
- **Q18:** "He resided in England and visited Holland, Germany, and France." The quote stitched two passages together
  with "…".

These two facts were probably true; they were dropped because the quotes didn't prove them.

### "Not in the sources" can mean "not found"

In a first run on Nov 25, which stopped partway when the OpenAI account ran out of credits, **Q6 "first job" came
back "not in the sources"**. But the Autobiography does say that at ten he was taken home to help in his father's
tallow-chandler business.

The search had missed it: the question's words ("first job") aren't the book's words. So I added a second search
for every question: a plain statement of the kind of passage that answers it. For Q6 that's "At a young age
{person} was taken from school and began working, helping in the family business or bound as an apprentice." In the
reviewed run, Q6 is answered from c1387 and c1460.

All 20 questions are now answered. 14 are only partly answered, with the gaps listed in the story file.

### Canary: passed

- **Question:** "Which U.S. coin, first issued in 1948, shows Benjamin Franklin's portrait?" The true answer is the
  Franklin half dollar.
- **Is the answer in the corpus?** No. I searched every chunk: none contains "half dollar", "half-dollar" or "1948",
  and the newest book is from 1917.
- **App's answer:** "Not in the sources."
- **The search did find near misses:** a chunk about a Franklin portrait hanging on a wall, and chunks about money and
  coinage (c3670, c3922, c3770 and others). The model didn't stretch them into an answer.

### Quality problems found (grounding was fine; the writing wasn't)

| Problem | Where |
|---|---|
| Same anecdote told twice | s26 and s27, the Howe joke |
| Repeats across paragraphs | "youngest son" in Q3 and Q4 (c1456 used by 4 sentences); John Collins in Q3 and Q14 |
| Too long and adult for a picture book | Q15 (three enemies and "proprietaries concentrated hatred" in one sentence); Q18 (four trips in one sentence) |
| Not suitable for young children | Q12 and Q13 mention his illegitimate son and an alleged child with Mrs. Foxcroft. These are sourced facts, but they don't belong in a picture book. |
| Source typo carried over | "Jared Ingersoli" (Ingersoll), spelled that way in the Gutenberg text. The story is faithful to its source. |
| A judgement, not a fact | Q11 "the hardest thing": each hardship is sourced, but the choice of which one is "hardest" is the model's |
| Noisy "missing" notes | Answers list every detail the snippets lack (exact dates, full lists), not just the parts the question asks |

**Fixed after this review**, in `lifestory.py`:

- The story prompt now says to tell each event once, keep sentences under about 20 words with at most three names
  each, and leave out facts about affairs, children born outside a marriage, cruelty or gore. The model may skip any
  fact but may never add one.
- The answer prompt now reports only missing parts that the question itself asks for.

The story handed in is the reviewed one, made before these fixes. Its log records the exact prompts that were used.

## Limits of the review

- **Same-model checker.** The checking model is the same kind as the writing model (gpt-5-mini), so they can share
  blind spots. That's why the mechanical check and the hand check exist.
- **What the mechanical check can't see.** It only checks names and numbers. A wrong verb or relationship ("his
  brother" when it was his uncle) gets past it, and is left to the model's check and to reading.
- **Omissions go unnoticed.** Neither check sees what's missing: the retrieved chunks may hold a better answer than the
  one written. The top-8 search can also miss the best passage entirely (as Q6 showed).
- **Old books.** The corpus is 19th- and early-20th-century biography, so the story inherits its viewpoint and its spellings.
