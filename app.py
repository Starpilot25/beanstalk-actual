"""
Jack and the Beanstalk storybook — MCON 368. First 3 pages + About Me, exported as one PDF.

Flow (each button click = exactly ONE API call; no loops or retries around any call):
  POST /api/hero    photo                       -> "Jack": a full-body character reference in the book style
  POST /api/page    hero + page number          -> one illustrated page (art only, no words)
  POST /api/adjust  an image + what to change   -> the same image with one thing changed (edit endpoint)
  POST /api/pdf     pages + About Me details    -> JackAndTheBeanstalk.pdf (no API call)

The API key is read from the OPENAI_API_KEY environment variable only.
"""

import base64
import io
import os
import threading
import time
from collections import defaultdict, deque

from flask import Flask, Response, jsonify, render_template, request
from openai import OpenAI
from PIL import Image, ImageOps

from book_pdf import build_pdf
from storyboard import CAST, CAST_SHEET, HANDS, PAGES, PAGES_BY_N, STYLE, ZONES

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
# Flask 3.1+ caps non-file form fields at 500 KB; images travel as base64 text fields.
app.config["MAX_FORM_MEMORY_SIZE"] = 40 * 1024 * 1024

# Model and quality are set in Render's Environment, so switching needs no code change.
#   IMAGE_MODEL=gpt-image-2.5-flare  default: far better pages (tested Oct 25), ~5c per page at medium
#   IMAGE_MODEL=gpt-image-1-mini     cheapest, but low quality gave waxy, broken scenes
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2.5-flare")
QUALITY = os.environ.get("IMAGE_QUALITY", "low")              # Jack + "change it" edits
PAGE_QUALITY = os.environ.get("PAGE_QUALITY", "medium")      # the story pages
# input_fidelity is only sent to models documented to accept it; others reject unknown params.
FIDELITY_MODELS = {"gpt-image-1", "gpt-image-1.5"}

_client = None


def client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set on the server.")
        # max_retries=0: the SDK's automatic retries would be a hidden loop around the call.
        _client = OpenAI(api_key=key, max_retries=0, timeout=170)
    return _client


# ---------------------------------------------------------------------------
# Prompts. STYLE and CAST come from storyboard.py and are identical in every call.
# Words we don't want in the picture are never named (naming them makes the model draw them).
# ---------------------------------------------------------------------------
NO_WORDS = "Pure illustration with no lettering anywhere."
# Same sentence in every page call: ties the look to the 3D Jack reference so pages don't drift
# into a flat, painted storybook style.
MATCH_RENDER = ("A full-bleed frame from a 3D computer-animated film, rendered exactly like the reference "
                "image: the same 3D modeling, materials, shading and lighting, with soft rounded 3D forms.")


def hero_prompt():
    others = " ".join(CAST[c] for c in ("mother", "cow", "old_man"))
    return (
        f"Art style: {STYLE} "
        "Create the cast reference sheet for a picture book, on one plain light background. "
        "LEFT HALF: a large head-and-shoulders close-up of the person in this photo as the hero, Jack, "
        "facing the viewer, the face filling most of that half, crisp and detailed. Keep their real "
        "face shape, eye shape, nose, mouth, eyebrows, skin tone, hair color, hair length and hairstyle, "
        "and their real age, so family would recognize them at a glance. Stylize the rendering, not the "
        "anatomy. Neutral, relaxed expression with the mouth closed. "
        "RIGHT HALF: a neat two-by-two grid of full-body views, each standing and facing the viewer: "
        "top left, the same Jack; top right, Jack's mother; bottom left, Milky-White the cow; "
        f"bottom right, the old man. Jack wears {CAST['jack'].split('wearing ', 1)[1]} {others} "
        f"{NO_WORDS}"
    )


def page_prompt(page):
    cast = " ".join(CAST[c] for c in page["cast"])
    return (
        f"Art style: {STYLE} "
        f"{MATCH_RENDER} {CAST_SHEET} {cast} "
        "Match Jack's face to the reference sheet, but his expression follows this page's mood. "
        f"Scene: {page['scene']} {page['shot']} {page['hands']} {HANDS} {page['mood']} {ZONES[page['zone']]} "
        f"Art style, again: {STYLE} {NO_WORDS}"
    )


def adjust_prompt(change, is_page):
    what = "storybook page" if is_page else "cast reference sheet"
    return (
        f"Art style: {STYLE} "
        f"Image 1 is a {what}; image 2 is the cast reference sheet. Edit image 1 with one change: "
        f"\"{change}\". Keep everything else exactly as it is - composition, characters, Jack's face "
        f"and clothes, colors and lighting. {NO_WORDS}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_png(raw: bytes, name: str, max_side=1024):
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        raise ValueError("That file isn't a readable image (use JPG, PNG or WEBP).")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def b64_field(name, label):
    raw = request.form.get(name, "")
    if not raw:
        raise ValueError(f"Missing {label}.")
    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        raise ValueError(f"The {label} was corrupted; make it again.")


def call_edit(images, prompt, size, quality=None):
    """Exactly one image-edit call. No retries, no loops."""
    extra = {"input_fidelity": "high"} if IMAGE_MODEL in FIDELITY_MODELS else {}
    result = client().images.edit(
        model=IMAGE_MODEL, image=images, prompt=prompt, size=size, quality=quality or QUALITY, n=1,
        output_format="jpeg", output_compression=90, **extra,
    )
    return result.data[0].b64_json


class Limiter:
    """Sliding one-hour window, kept in memory (resets when Render restarts the app)."""

    def __init__(self, limit):
        self.limit, self.hits, self.lock = limit, defaultdict(deque), threading.Lock()

    def _trim(self, q, now):
        while q and now - q[0] > 3600:
            q.popleft()

    def take(self, key):
        """Use one slot. Returns (allowed, slots_left, seconds_until_next_slot)."""
        now = time.time()
        with self.lock:
            q = self.hits[key]
            self._trim(q, now)
            if len(q) >= self.limit:
                return False, 0, int(3600 - (now - q[0])) + 1
            q.append(now)
            return True, self.limit - len(q), 0

    def refund(self, key):
        with self.lock:
            if self.hits[key]:
                self.hits[key].pop()


requests_per_ip = Limiter(int(os.environ.get("HOURLY_LIMIT", "20")))           # any API call
edits_per_ip = Limiter(int(os.environ.get("EDITS_PER_HOUR", "5")))             # "Change it" per person
books_per_ip = Limiter(int(os.environ.get("BOOKS_PER_HOUR", "3")))              # cast sheets per person
books_site = Limiter(int(os.environ.get("SITE_BOOKS_PER_HOUR", "20")))          # cast sheets, everyone


def client_ip():
    # Render's proxy appends the real client address as the LAST entry; earlier entries can be faked.
    fwd = request.headers.get("X-Forwarded-For", "")
    return (fwd.split(",")[-1].strip() if fwd else request.remote_addr) or "?"


def rate_limited():
    return not requests_per_ip.take(client_ip())[0]


def minutes(sec):
    m = max(1, round(sec / 60))
    return f"{m} minute{'s' if m != 1 else ''}"


def error(msg, code=400):
    return jsonify({"error": msg}), code


def api_error(e):
    app.logger.exception("API call failed")
    msg = getattr(e, "message", None) or str(e)
    low = msg.lower()
    if "safety" in low or "moderation" in low:
        msg = "The image service declined this request. Try a different photo or wording."
    elif "verif" in low:
        msg = "Your OpenAI organization must be verified to use image models."
    return error(f"Generation failed: {msg}", 502)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html", pages=PAGES, model=IMAGE_MODEL, books_per_hour=books_per_ip.limit, edits_per_hour=edits_per_ip.limit)


@app.get("/healthz")
def health():
    return "ok"


@app.post("/api/hero")
def hero():
    if rate_limited():
        return error(f"You've reached {requests_per_ip.limit} pictures this hour. Try again later.", 429)
    f = request.files.get("photo")
    if not f or not f.filename:
        return error("Please upload or take a photo.")
    try:
        photo = to_png(f.read(), "photo.png")
    except ValueError as e:
        return error(str(e))
    # Each cast sheet starts a new book, so this is where books are counted.
    ip = client_ip()
    ok, left, wait = books_per_ip.take(ip)
    if not ok:
        return error(f"You've made {books_per_ip.limit} books this hour. You can start another in about {minutes(wait)}.", 429)
    site_ok, _, site_wait = books_site.take("all")
    if not site_ok:
        books_per_ip.refund(ip)
        return error(f"The site has hit its limit of {books_site.limit} books this hour. Try again in about {minutes(site_wait)}.", 429)
    try:
        image = call_edit(photo, hero_prompt(), "1536x1024", PAGE_QUALITY)  # the sheet every page copies
    except Exception as e:
        books_per_ip.refund(ip)   # a failed attempt doesn't use up a book
        books_site.refund("all")
        return api_error(e)
    return jsonify({"image": image, "books_left": left})


@app.post("/api/page")
def page():
    if rate_limited():
        return error(f"You've reached {requests_per_ip.limit} pictures this hour. Try again later.", 429)
    try:
        p = PAGES_BY_N.get(int(request.form.get("n", 0)))
        if not p:
            raise ValueError("Unknown page.")
        hero_ref = to_png(b64_field("hero", "Jack reference"), "jack.png")
    except ValueError as e:
        return error(str(e))
    try:
        # One reference image (Jack) + the same style and cast strings on every page.
        return jsonify({"image": call_edit(hero_ref, page_prompt(p), "1536x1024", PAGE_QUALITY)})
    except Exception as e:
        return api_error(e)


@app.post("/api/adjust")
def adjust():
    if rate_limited():
        return error(f"You've reached {requests_per_ip.limit} pictures this hour. Try again later.", 429)
    try:
        change = " ".join(str(request.form.get("change", "")).split())[:240].replace('"', "'")
        if not change:
            raise ValueError("Say what to change, like “make the cow whiter”.")
        target = request.form.get("target", "")
        is_page = target != "hero"
        if is_page and int(target or 0) not in PAGES_BY_N:
            raise ValueError("Unknown page.")
        image = to_png(b64_field("image", "picture"), "image.png", max_side=1536)
        hero_ref = to_png(b64_field("hero", "Jack reference"), "jack.png")
    except ValueError as e:
        return error(str(e))
    size = "1536x1024"  # pages and the Jack sheet are both landscape
    ip = client_ip()
    ok, left, wait = edits_per_ip.take(ip)
    if not ok:
        return error(f"You've used your {edits_per_ip.limit} changes this hour. You can make another in about "
                     f"{minutes(wait)}, or repaint the page instead.", 429)
    try:
        image_out = call_edit([image, hero_ref], adjust_prompt(change, is_page), size, PAGE_QUALITY)
    except Exception as e:
        edits_per_ip.refund(ip)   # a failed attempt doesn't use up a change
        return api_error(e)
    return jsonify({"image": image_out, "edits_left": left})


@app.post("/api/pdf")
def pdf():
    data = request.get_json(silent=True) or {}
    name = " ".join(str(data.get("name", "")).split())[:40]
    if not name:
        return error("Add the child's name for the About Me page.")
    about = {
        "age": " ".join(str(data.get("age", "")).split())[:20],
        "likes": str(data.get("likes", "")).strip()[:300],
        "about": str(data.get("about", "")).strip()[:600],
    }
    try:
        images = {}
        for p in PAGES:
            raw = data.get("pages", {}).get(str(p["n"]))
            if not raw:
                raise ValueError(f"Page {p['n']} hasn't been made yet.")
            images[p["n"]] = base64.b64decode(raw, validate=True)
        hero_img = base64.b64decode(data.get("hero", ""), validate=True) if data.get("hero") else None
    except ValueError as e:
        return error(str(e))
    except Exception:
        return error("A page image was corrupted; make it again.")
    pdf_bytes = build_pdf(PAGES, images, name, about, hero_img)
    return Response(pdf_bytes, mimetype="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="JackAndTheBeanstalk.pdf"'})


@app.errorhandler(413)
def too_big(_):
    return error("That request was too large. Try a smaller photo.", 413)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
