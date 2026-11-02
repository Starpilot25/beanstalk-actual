# Jack and the Beanstalk, starring your child — MCON 368

Upload one photo → the child becomes Jack → paint pages 1–3 → download `JackAndTheBeanstalk.pdf`
(3 story pages + an About Me page).

## How it works
Sign in with Google. Every book you make is saved to your account (cast sheet, pages, About Me), so it is
still there when you come back. Each picture is one API call with no retries; "Paint all pages" sends the
page requests at the same time and the server paints them in parallel threads, each with its own progress bar.

| Step | Endpoint | API calls |
|---|---|---|
| Make the cast sheet (starts a new saved book) | `POST /api/books` | 1 image edit |
| Paint page *n* | `POST /api/books/<id>/pages/<n>` | 1 image edit |
| Change one thing on the sheet or a page | `POST /api/books/<id>/adjust` | 1 image edit |
| Save About Me details | `PATCH /api/books/<id>` | none |
| Download the PDF (built from the saved book) | `GET /api/books/<id>/pdf` | none |
| Your recent activity log | `GET /api/activity` | none |

**Storage:** Postgres (`DATABASE_URL`). Tables are `users`, `books`, `pages` (JPEG images) and `events` (the
generation log). The uploaded photo is never stored. Locally, without `DATABASE_URL`, a SQLite file is used.

**Logging:** every image call, PDF and sign-in is written to the server log (Render → Logs) and the
`events` table, with the user, book, action, model, duration and success or failure.

**Limits (per signed-in user, per hour):** 3 new books, 5 changes and 20 pictures in total; 20 new
books per hour site-wide. They are kept in memory and reset when the app restarts.

## Keeping the book consistent
- **One reference image.** A cast sheet is drawn once: a large close-up of the child as Jack on the left, and full-body Jack, his mother, Milky-White and the old man on the right. Every page call sends that same image, so the whole cast stays the same from page to page.
- **One style string.** `STYLE` in `storyboard.py` is sent word for word in every call and never changes.
- **Fixed cast descriptions.** The mother, Milky-White and the old man are described in `CAST` once and reused word for word.
- **No words in the art.** The image model never draws text. The PDF layer (`book_pdf.py`) prints the story text in Young Serif over a soft fade in each page's quiet area (lower third, sky, or dark grass).

## Files
- `storyboard.py` — the book as data: style, cast, and one entry per page. Add page 4 by appending to `PAGES`.
- `app.py` — Flask routes and prompt assembly.
- `book_pdf.py` — PDF layout (reportlab).
- `templates/index.html` — the web page.
- `PROMPTS.md` — how the prompts were developed and tested.
- `to-do.md` — what still needs work.

## Settings (Render → Environment)
| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | — | required; never in code or the repo |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | from Google Cloud → Credentials (OAuth client, Web application) |
| `SECRET_KEY` | — | long random string; signs the login cookie |
| `CONTACT_EMAIL` | — | shown on the privacy page as the contact for account deletion |
| `LOGIN_PASSWORD` | off | optional shared password sign-in (name + password). Set it only in Render, never in the repo |
| `DATABASE_URL` | local SQLite | Render Postgres "Internal Database URL" |
| `IMAGE_MODEL` | `gpt-image-2.5-flare` | `fake` = free placeholder pictures for testing (no OpenAI calls). `gpt-image-1-mini` is cheaper but gave waxy, broken scenes |
| `PAGE_QUALITY` | `medium` | quality for every picture: cast sheet, pages and "Change it" edits (~5¢ each); `low` looked smeared |
| `BOOKS_PER_HOUR` | `3` | new books (cast sheets) per person per hour; failed attempts don't count |
| `SITE_BOOKS_PER_HOUR` | `20` | new books per hour across everyone, a ceiling on spending (~20¢ per book) |
| `EDITS_PER_HOUR` | `5` | "Change it" edits per person per hour; failed attempts don't count |
| `HOURLY_LIMIT` | `20` | all pictures per person per hour (sheets, pages, edits): enough for 3 books plus a few repaints, ~$1/hour max |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
IMAGE_MODEL=fake DEV_LOGIN=1 python app.py   # free test images + a local test sign-in, http://localhost:5000
```
`DEV_LOGIN` is ignored on Render, so the test sign-in can never be used on the live site.

Font: Young Serif, SIL Open Font License (`fonts/OFL-YoungSerif.txt`).
