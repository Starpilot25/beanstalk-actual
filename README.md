# Jack and the Beanstalk, starring your child — MCON 368

Upload one photo → the child becomes Jack → paint pages 1–3 → download `JackAndTheBeanstalk.pdf`
(3 story pages + an About Me page).

## How it works
| Step | Endpoint | API calls |
|---|---|---|
| Turn the child into Jack (full-body character reference) | `POST /api/hero` | 1 image edit (photo → Jack) |
| Paint a page | `POST /api/page` | 1 image edit (Jack reference → page) |
| Change one thing on Jack or a page | `POST /api/adjust` | 1 image edit (existing image + Jack → same image, one change) |
| Build the PDF | `POST /api/pdf` | none |

Every click is exactly one API call; there are no loops, and the SDK's automatic retries are off (`max_retries=0`).

## Keeping the book consistent
- **One reference image.** Jack is drawn once, as a full-body reference in his outfit. Every page call sends that same image.
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
| `IMAGE_MODEL` | `gpt-image-1-mini` | cheapest. `gpt-image-2.5-flare` is OpenAI's newer everyday model; try it if pages look weak |
| `IMAGE_QUALITY` | `low` | quality for Jack and the "Change it" edits |
| `PAGE_QUALITY` | same as `IMAGE_QUALITY` | quality for the story pages; `medium` is sharper and costs more |
| `HOURLY_LIMIT` | `40` | requests per IP per hour |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then put your key in .env (git-ignored)
export $(cat .env)      # Windows: set OPENAI_API_KEY=sk-...
python app.py           # http://localhost:5000
```

Font: Young Serif, SIL Open Font License (`fonts/OFL-YoungSerif.txt`).
