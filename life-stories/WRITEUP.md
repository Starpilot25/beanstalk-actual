# Life stories: what I did

**Live:** https://beanstalk.autosignusa.com/life (sign in, then open **Life stories**).

**Hand-in files:**

- The story: [online](https://beanstalk.autosignusa.com/life/s/gH-XRIZjUIMp) and as [`franklin-story.md`](franklin-story.md).
- The log: [online](https://beanstalk.autosignusa.com/life/s/gH-XRIZjUIMp/log) and as [`franklin-log.json`](franklin-log.json).
- The review of the log: [`LOG-REVIEW.md`](LOG-REVIEW.md).
- The code: [`lifestory.py`](../lifestory.py).

## What it does

Upload pages about one person, and the app writes a children's life story from those pages, and only from them.
Every sentence shows the chunk IDs it came from, and you can tap any of them to read the passage.

1. **Upload.** Upload files (PDF, HTML, EPUB, Word or text) or paste links. Project Gutenberg book pages work as
   they are: Gutenberg refuses cloud servers, so the app falls back to Gutenberg's own mirror. Collections can be
   added to in batches, and any document can be removed.
2. **Chunk.** Each document is cut into pieces of about 1,000 characters, at sentence ends, with one sentence of
   overlap. Each chunk keeps its document and page (the PDF's own page, or an estimated one).
3. **Embed and store.** Each chunk gets an embedding from OpenAI `text-embedding-3-small` (512 numbers), stored in
   Postgres next to its text. A 1,400-page corpus costs about 1¢ to embed.
4. **Retrieve.** Each of the 20 questions is searched three ways, with `{person}` filled in:
   - by meaning, with the question itself;
   - by meaning, with a plain statement of the kind of passage that answers it;
   - by keywords (BM25), with the person's name left out because it's in every chunk.

   The three rankings are merged, and the top 8 chunks go to the model.
5. **Answer, from the snippets only.** For each question the model gets the 8 chunks and nothing else. Every fact it
   reports must give a chunk ID and an exact quote from that chunk.

   The app then checks each quote word for word against the chunk. A fact that fails, or that cites a chunk not
   retrieved for that question, is thrown out. If nothing is left, the answer is **"Not in the sources."** and the
   story skips that question.
6. **Write.** A second call writes the picture-book story from the checked facts only. Each sentence must list the
   facts it uses, which map to chunk IDs.
7. **Check for training data.** Every sentence is sent back with the text of the chunks it cites. Anything those
   chunks don't say is flagged as probably coming from the model's training. A flagged sentence is rewritten from its
   chunks once and checked again; if it still fails, it's removed. Both outcomes show on the story page.
8. **Canary.** An optional question whose true answer isn't in the pages. It passes if the answer is "not in the
   sources".
9. **Log.** Every query, the chunk IDs it retrieved (with meaning and keyword scores), and every prompt sent and reply
   received are saved. They can be viewed as a page, as JSON, or as the story in Markdown with every cited chunk.

It works for any person: nothing in the code, the questions or the prompts is about Franklin.

## Franklin results

- **Corpus:** 5 Project Gutenberg biographies, about 1,398 pages in 4,534 chunks.
- **Questions:** 20 of 20 answered from the pages (14 of them only partly).
- **Story:** 59 sentences, and every one cites a chunk.
- **Training data:**
  - The app's check, the review script and my hand check all find nothing from training in the story.
  - Two facts whose quotes weren't word for word in their chunks were thrown out before writing.
- **Canary:** "Which U.S. coin, first issued in 1948, shows Franklin's portrait?" The answer, the half dollar, isn't in
  the corpus; the app said "Not in the sources." Passed.
- **Time and cost:** 143 seconds and about 7¢ of model calls per story.

## What the review found and what I changed

Details are in [`LOG-REVIEW.md`](LOG-REVIEW.md).

- **A missed answer that looked like an absence.** In an earlier run, the search answered "first job" with "not in
  the sources", though the Autobiography says it. I added the second, plain-language search per question, and it's
  now answered.
- **A story that read like a list.** It said "He…", gave two birth dates back to back and used long sentences. I
  rewrote the story instructions so the story uses the person's name, joins facts into sentences, and handles sources
  that disagree with "some books say…".
- **Still left after that** (fixed in the prompts after the reviewed run):
  - a repeated anecdote;
  - adult sentences and facts not suitable for young children;
  - noisy "missing" notes.

## How to test it with your own corpus

1. Sign in and open **Life stories**. Choose **New person…** and type the person's name.
2. Add files or links. Wait until every document says "added". Each row shows its pages and chunks; anything that
   couldn't be read says why.
3. Optionally, type a canary question. `{person}` is filled in for you. Then click **Write the story**. It takes
   about 2 to 3 minutes.
4. The story page has:
   - the story, with a chunk number after every sentence;
   - the checks and the canary;
   - all 20 answers, with their facts, quotes and retrieved chunks;
   - links to the full log.

   Download the log as JSON and run `python review_log.py log.json` to check it yourself.

The Franklin collection appears to every signed-in user as an example, so it can be used without uploading anything.
