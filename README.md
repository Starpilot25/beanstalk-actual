# Jack and the Beanstalk, starring your child — MCON 368

Upload one photo → the child becomes Jack → paint pages 1–3 → download `JackAndTheBeanstalk.pdf`
(3 story pages + an About Me page).

## How it works
| Step | Endpoint | API calls |
|---|---|---|
| Make the cast sheet: the child's face close-up as Jack + full-body Jack, mother, cow, old man | `POST /api/hero` | 1 image edit (photo → Jack) |
| Paint a page | `POST /api/page` | 1 image edit (Jack reference → page) |
| Change one thing on Jack or a page | `POST /api/adjust` | 1 image edit (existing image + Jack → same image, one change) |
| Build the PDF | `POST /api/pdf` | none |

Every click is exactly one API call; there are no loops, and the SDK's automatic retries are off (`max_retries=0`).

Limits: each new cast sheet starts a book. Each person can start 3 books, make 5 changes and 20 pictures in total an hour; the whole site, 20 books. Limits live in memory, so they reset if Render restarts the app.

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
| `IMAGE_MODEL` | `gpt-image-2.5-flare` | `gpt-image-1-mini` is cheaper but gave waxy, broken scenes in testing |
| `PAGE_QUALITY` | `medium` | quality for every picture: cast sheet, pages and "Change it" edits (~5¢ each); `low` looked smeared |
| `BOOKS_PER_HOUR` | `3` | new books (cast sheets) per person per hour; failed attempts don't count |
| `SITE_BOOKS_PER_HOUR` | `20` | new books per hour across everyone, a ceiling on spending (~20¢ per book) |
| `EDITS_PER_HOUR` | `5` | "Change it" edits per person per hour; failed attempts don't count |
| `HOURLY_LIMIT` | `20` | all pictures per person per hour (sheets, pages, edits): enough for 3 books plus a few repaints, ~$1/hour max |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then put your key in .env (git-ignored)
export $(cat .env)      # Windows: set OPENAI_API_KEY=sk-...
python app.py           # http://localhost:5000
```

Font: Young Serif, SIL Open Font License (`fonts/OFL-YoungSerif.txt`).
