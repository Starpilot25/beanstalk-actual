# Storybook starring your child — MCON 368

Upload one photo, pick *Jack and the Beanstalk* or *Little Red Riding Hood*, and get a cover, 20 illustrated pages
and an About Me page as a PDF with the child as the hero. $0.99 a book, paid from a balance funded through Stripe
(test mode).

Live: https://beanstalk.autosignusa.com

## How a book is made

| Step | When | Calls |
|---|---|---|
| **Character bible**: every supporting character (Jack's mother, Milky-White, the giant, the wolf, Grandma…) drawn once on a plain background | once, from `/admin` | 1 image each |
| **Pre-made scenes**: all 20 pages of each story drawn with those characters as references, leaving an empty spot for the hero; each is checked and redrawn up to 3 times | once, from `/admin` | 1 image + 1 check each |
| **Hero sheet**: the photo becomes the hero (face close-up + full length, in the story's costume) | per book | 1 image + 1 check (up to 3) |
| **Pages**: the hero is edited into the 15 pre-made scenes that have a hero slot, all at once | per book | 1 image + 1 check per page, up to 3 tries |
| **PDF**: laid out by the shared template, stored in the database | per book | none |

Five pages per story (the beanstalk growing overnight, the castle, the wolf in the bed…) have no hero, so
they are the pre-made scenes as they are. That keeps a book to 16 image calls on a good run, which matters
for the 60-second target and the account's images-per-minute limit.

**One template, two stories.** `TEMPLATE` in `stories.py` fixes, for each of the 20 pages, the layout, the
camera shot, where the hero stands and where words may go. Both stories fill the same 20 slots, so page *k* of
either book has the same layout.

**The quality loop.** Every generated picture goes to a vision model (`ANALYSIS_MODEL`, default `gpt-5-mini`)
that scores the hero's likeness to the hero sheet, whether the page shows the right scene, anatomy (hands),
and cleanliness (no drawn letters), and maps where faces and important things are on a 3×3 grid. A page
that doesn't pass is repainted, up to 3 attempts in total; if none pass, the best-scoring one is kept. Every
attempt is stored (`page_attempts`), and the UI shows the attempt count on every picture.

**Text never hides the story.** The image model never draws words; the PDF prints them in Young Serif. On a
full-bleed page the words go in the template's preferred band (top, middle or bottom third) only if the
analysis found no faces or important things in that band; the pre-made scenes are checked for that band
too. If no allowed band is clear, the page switches to the framed layout: the art sits in a frame and the
words go on the paper below it, where they cannot cover anything.

**Speed.** The book is made by a background thread on the server, so it survives a refresh. The browser
polls the progress (stage name, every page's status and attempt count) and shows each thumbnail as soon as
it exists. Pages are painted in parallel (`PAGE_WORKERS`), paced by `IMAGES_PER_MINUTE`. No new repaint
starts after `RETRY_DEADLINE` seconds, so a slow book still finishes. The PDF is built once and stored, so
downloads are instant, also after signing out and back in.

## Money (Stripe test mode)

- **Add funds** → Stripe Checkout (test card `4242 4242 4242 4242`). When Stripe sends the user back, the
  session is looked up on Stripe's side and credited once (the session id is a unique key in the ledger).
- **A book** takes $0.99 when it starts, in the same locked transaction that checks the balance, so the
  balance can never go negative. If the book fails, the $0.99 is put back automatically.
- **Refunds** are requested from the history, then processed: a book's $0.99 back to the balance, or unused
  balance back to the card through Stripe's Refund API.
- **History** (`/wallet`): every credit and debit with its cause, amount, time and the balance after it,
  plus a check that the rows add up to the balance.
- **Cost per book**: every API call is logged in `api_calls` with its dollar cost, computed from the token
  usage OpenAI returns. `/wallet` shows the average cost per finished book (first tries, repaints and
  analysis checks, split out) next to the $0.99 price. The one-time cost of the shared art is shown separately.

## Files
- `stories.py` — the template, both stories, the character bible text, and every prompt.
- `pipeline.py` — image and analysis calls with cost logging, the rate limiter, the quality loop, the book job.
- `billing.py` — Stripe checkout, charging, refunds.
- `book_pdf.py` — the PDF layouts.
- `db.py` — tables: `users`, `storybooks`, `book_pages`, `page_attempts`, `bible`, `scenes`, `ledger`, `refunds`, `api_calls`.
- `app.py` — routes. `templates/` — the pages.
- `review-log.md` — every run of the grading skill, oldest first. `to-do.md` — known defects.

## Settings (Render → Environment)
| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | — | required; never in code or the repo |
| `STRIPE_SECRET_KEY` | — | the class **test** key (`sk_test_…`); never in code or the repo. Without it a pretend checkout is used |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Google sign-in |
| `SECRET_KEY` | — | long random string; signs the login cookie |
| `ADMIN_EMAILS` | — | comma-separated emails that can open `/admin` |
| `DATABASE_URL` | local SQLite | Render Postgres "Internal Database URL" |
| `LOGIN_PASSWORD` | off | optional shared password sign-in |
| `IMAGE_MODEL` | `gpt-image-2.5-flare` | `fake` = free placeholder pictures and fake checks, for testing |
| `PAGE_QUALITY` / `HERO_QUALITY` / `SCENE_QUALITY` | `medium` (all three) | image quality per kind of call; keep scenes and pages the same so every page matches |
| `ANALYSIS_MODEL` | `gpt-5-mini` | the vision model that checks every picture |
| `IMAGES_PER_MINUTE` | `20` | your OpenAI tier's image limit for the model |
| `PAGE_WORKERS` | `16` | pages painted at the same time |
| `RETRY_DEADLINE` | `48` | seconds after upload after which no new repaint starts |
| `BOOKS_PER_HOUR` / `SITE_BOOKS_PER_HOUR` | `6` / `30` | limits per person and site-wide |
| `PRICE_*` | Nov 2026 prices | $ per 1M tokens used for the cost log |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
IMAGE_MODEL=fake DEV_LOGIN=1 IMAGES_PER_MINUTE=500 python app.py   # free pictures, pretend Stripe, local sign-in
```
Then sign in with the local test sign-in, open `/admin` and draw the shared art (free in fake mode).

Font: Young Serif, SIL Open Font License (`fonts/OFL-YoungSerif.txt`).
