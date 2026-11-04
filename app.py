"""
Jack and the Beanstalk storybook — MCON 368.

Sign in with Google -> your books are saved and come back on every visit.

  POST /api/books                    photo + About Me     -> new book with its cast sheet   (1 image call)
  POST /api/books/<id>/pages/<n>     -                    -> paint page n                   (1 image call)
  POST /api/books/<id>/adjust        target + change      -> edit the sheet or one page     (1 image call)
  PATCH /api/books/<id>              About Me details     -> save details                   (no call)
  GET  /api/books/<id>/pdf           -                    -> JackAndTheBeanstalk.pdf        (no call)

"Paint all pages" sends the page requests at the same time; the server handles them in parallel
threads (gunicorn --threads), one image call per request, no retries.

Secrets (OPENAI_API_KEY, GOOGLE_CLIENT_ID/SECRET, SECRET_KEY, DATABASE_URL) come from the environment only.
"""

import base64
import hmac
import io
import logging
import os
import random
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps
from werkzeug.middleware.proxy_fix import ProxyFix

import db
from book_pdf import build_pdf
from storyboard import CAST, CAST_SHEET, HANDS, JACK_OUTFIT, JACK_OUTFIT_SKIRT, PAGES, PAGES_BY_N, STYLE, ZONES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("beanstalk")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)   # Render terminates HTTPS
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(32)        # set SECRET_KEY on Render!
app.config.update(
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,
    MAX_FORM_MEMORY_SIZE=20 * 1024 * 1024,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30,                       # stay signed in 30 days
)

# Image model. IMAGE_MODEL=fake draws free placeholder pictures for testing (no OpenAI calls).
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2.5-flare")
PAGE_QUALITY = os.environ.get("PAGE_QUALITY", "medium")
FIDELITY_MODELS = {"gpt-image-1", "gpt-image-1.5"}
FAKE = IMAGE_MODEL == "fake"

# ---------------------------------------------------------------------------
# Google sign-in (OpenID Connect)
# ---------------------------------------------------------------------------
oauth = OAuth(app)
oauth.register(
    "google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)
DEV_LOGIN = os.environ.get("DEV_LOGIN") == "1" and not os.environ.get("RENDER")  # local testing only
# Optional shared password sign-in (e.g. for the professor or testers without Google).
# The password lives only in the environment, never in the public repo. Unset = feature off.
LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD", "")


def current_user_id():
    return session.get("uid")


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user_id():
            return error("Please sign in with Google first.", 401)
        return fn(*a, **kw)
    return wrapper


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
_client = None


def client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set on the server.")
        _client = OpenAI(api_key=key, max_retries=0, timeout=170)   # no hidden retry loop
    return _client


# ---------------------------------------------------------------------------
# Prompts. STYLE and CAST come from storyboard.py and are identical in every call.
# ---------------------------------------------------------------------------
NO_WORDS = "Pure illustration with no lettering anywhere."
MATCH_RENDER = ("A full-bleed frame from a 3D computer-animated film, rendered exactly like the reference "
                "image: the same 3D modeling, materials, shading and lighting, with soft rounded 3D forms.")


def hero_prompt():
    others = " ".join(CAST[c] for c in ("mother", "cow"))   # recurring characters only
    return (
        f"Art style: {STYLE} "
        "Create the cast reference sheet for a picture book, on one plain light background. "
        "LEFT HALF: a large head-and-shoulders close-up of the person in this photo as the hero, Jack, "
        "facing the viewer, the face filling most of that half, crisp and detailed. Keep their real "
        "face shape, eye shape, nose, mouth, eyebrows, skin tone, hair color, hair length and hairstyle, "
        "and their real age, so family would recognize them at a glance. Stylize the rendering, not the "
        "anatomy. Neutral, relaxed expression with the mouth closed. "
        "RIGHT HALF: full-body views of the recurring cast. Across the top, the same Jack and Jack's "
        "mother standing side by side, facing the viewer, head to toe; across the bottom, Milky-White "
        "the cow standing in side view. "
        f"If the person in the photo is a girl or a woman, Jack wears {JACK_OUTFIT_SKIRT}; "
        f"otherwise Jack wears {JACK_OUTFIT}. Draw the same outfit in the close-up and the full-body view. {others} "
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
# Image generation (one call, logged)
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


def fake_image(label):
    """Free placeholder for testing: a labeled picture after a short, realistic-feeling wait."""
    time.sleep(float(os.environ.get("FAKE_DELAY", "4")) * random.uniform(0.6, 1.4))
    rng = random.Random(label)
    im = Image.new("RGB", (1536, 1024), tuple(rng.randint(90, 200) for _ in range(3)))
    d = ImageDraw.Draw(im)
    d.ellipse((620, 260, 916, 560), fill=(232, 196, 160))
    d.rectangle((690, 560, 846, 860), fill=(110, 80, 50))
    d.text((40, 40), f"TEST IMAGE - {label}", fill=(255, 255, 255))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def generate(images, prompt, *, uid, book_id, action, target, label):
    """Exactly one image call (or a free fake). Returns JPEG bytes. Logs to stdout and the events table."""
    t0 = time.time()
    try:
        if FAKE:
            out = fake_image(label)
        else:
            extra = {"input_fidelity": "high"} if IMAGE_MODEL in FIDELITY_MODELS else {}
            r = client().images.edit(model=IMAGE_MODEL, image=images, prompt=prompt, size="1536x1024",
                                     quality=PAGE_QUALITY, n=1, output_format="jpeg",
                                     output_compression=90, **extra)
            out = base64.b64decode(r.data[0].b64_json)
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        log.warning("generate FAIL user=%s book=%s action=%s target=%s model=%s ms=%d err=%s",
                    uid, book_id, action, target, IMAGE_MODEL, ms, str(e)[:200])
        db.log_event(user_id=uid, book_id=book_id, action=action, target=str(target), model=IMAGE_MODEL,
                     ms=ms, ok=0, detail=str(e)[:300])
        raise
    ms = int((time.time() - t0) * 1000)
    log.info("generate OK user=%s book=%s action=%s target=%s model=%s ms=%d bytes=%d",
             uid, book_id, action, target, IMAGE_MODEL, ms, len(out))
    db.log_event(user_id=uid, book_id=book_id, action=action, target=str(target), model=IMAGE_MODEL,
                 ms=ms, ok=1, detail=f"{len(out)} bytes")
    return out


# ---------------------------------------------------------------------------
# Limits (per signed-in user now, not per IP)
# ---------------------------------------------------------------------------
class Limiter:
    """Sliding one-hour window, kept in memory (resets when Render restarts the app)."""

    def __init__(self, limit):
        self.limit, self.hits, self.lock = limit, defaultdict(deque), threading.Lock()

    def take(self, key):
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 3600:
                q.popleft()
            if len(q) >= self.limit:
                return False, 0, int(3600 - (now - q[0])) + 1
            q.append(now)
            return True, self.limit - len(q), 0

    def refund(self, key):
        with self.lock:
            if self.hits[key]:
                self.hits[key].pop()


pictures_per_user = Limiter(int(os.environ.get("HOURLY_LIMIT", "20")))
edits_per_user = Limiter(int(os.environ.get("EDITS_PER_HOUR", "5")))
books_per_user = Limiter(int(os.environ.get("BOOKS_PER_HOUR", "3")))
books_site = Limiter(int(os.environ.get("SITE_BOOKS_PER_HOUR", "20")))
failed_logins = Limiter(10)   # wrong passwords per address per hour


def minutes(sec):
    m = max(1, round(sec / 60))
    return f"{m} minute{'s' if m != 1 else ''}"


def error(msg, code=400):
    return jsonify({"error": msg}), code


def api_error(e):
    msg = getattr(e, "message", None) or str(e)
    low = msg.lower()
    if "safety" in low or "moderation" in low:
        msg = "The image service declined this request. Try a different photo or wording."
    elif "verif" in low:
        msg = "Your OpenAI organization must be verified to use image models."
    return error(f"Generation failed: {msg}", 502)


def take_picture_slot(uid):
    ok, _, wait = pictures_per_user.take(uid)
    return None if ok else error(f"You've reached {pictures_per_user.limit} pictures this hour. "
                                 f"Try again in about {minutes(wait)}.", 429)


def clean_details(src):
    return {
        "child_name": " ".join(str(src.get("child_name", "")).split())[:40],
        "age": " ".join(str(src.get("age", "")).split())[:20],
        "likes": str(src.get("likes", "")).strip()[:300],
        "about": str(src.get("about", "")).strip()[:600],
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    uid = current_user_id()
    user = db.get_user(uid) if uid else None
    if uid and not user:          # stale cookie (e.g. database was reset)
        session.clear()
    return render_template("index.html", pages=PAGES, model=IMAGE_MODEL, user=user, fake=FAKE,
                           dev_login=DEV_LOGIN, password_login=bool(LOGIN_PASSWORD), books_per_hour=books_per_user.limit,
                           edits_per_hour=edits_per_user.limit)


@app.get("/privacy")
def privacy():
    return render_template("privacy.html", updated="November 2, 2026", contact=os.environ.get("CONTACT_EMAIL", ""))


@app.get("/healthz")
def health():
    return "ok"


@app.get("/login")
def login():
    if DEV_LOGIN and request.args.get("dev"):
        uid = db.upsert_user("dev-" + request.args["dev"], f"{request.args['dev']}@example.com",
                             request.args["dev"].title(), None)
        session.permanent = True
        session["uid"] = uid
        return redirect(url_for("index"))
    try:
        return oauth.google.authorize_redirect(url_for("auth_callback", _external=True))
    except Exception as e:   # Google unreachable or credentials missing
        log.warning("login start FAIL err=%s", str(e)[:200])
        return redirect(url_for("index", login="failed"))


@app.post("/login/password")
def login_password():
    if not LOGIN_PASSWORD:
        abort(404)
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[-1].strip() or request.remote_addr or "?")
    name = " ".join(str(request.form.get("name", "")).split())[:40]
    pw = str(request.form.get("password", ""))
    if not failed_logins.take(ip)[0]:
        return redirect(url_for("index", login="locked"))
    if len(name) < 2 or not hmac.compare_digest(pw.encode(), LOGIN_PASSWORD.encode()):
        log.warning("password login FAIL ip=%s name=%s", ip, name)
        return redirect(url_for("index", login="badpw"))
    failed_logins.refund(ip)              # only failed attempts count toward the lockout
    uid = db.upsert_user("pw:" + name.lower(), name, name, None)
    session.permanent = True
    session["uid"] = uid
    log.info("password login OK user=%s name=%s", uid, name)
    db.log_event(user_id=uid, action="login", ok=1, detail=f"password:{name}")
    return redirect(url_for("index"))


@app.get("/auth/callback")
def auth_callback():
    try:
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or oauth.google.userinfo()
    except Exception as e:
        log.warning("login FAIL err=%s", e)
        return redirect(url_for("index", login="failed"))
    uid = db.upsert_user(info["sub"], info.get("email", ""), info.get("name", ""), info.get("picture"))
    session.permanent = True
    session["uid"] = uid
    log.info("login OK user=%s email=%s", uid, info.get("email"))
    db.log_event(user_id=uid, action="login", ok=1, detail=info.get("email", "")[:300])
    return redirect(url_for("index"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Books API
# ---------------------------------------------------------------------------
@app.get("/api/books")
@login_required
def books_list():
    out = []
    for b in db.list_books(current_user_id()):
        out.append({"id": b["id"], "child_name": b["child_name"], "pages": b["page_count"],
                    "updated": b["updated_at"].isoformat() if b["updated_at"] else None})
    return jsonify(out)


@app.get("/api/books/<int:book_id>")
@login_required
def book_get(book_id):
    b = db.get_book(current_user_id(), book_id)
    if not b:
        return error("Book not found.", 404)
    b["updated_at"] = b["updated_at"].isoformat() if b["updated_at"] else None
    return jsonify(b)


@app.post("/api/books")
@login_required
def book_create():
    """Upload a photo -> make the cast sheet -> a new saved book."""
    uid = current_user_id()
    f = request.files.get("photo")
    if not f or not f.filename:
        return error("Please upload or take a photo.")
    try:
        photo = to_png(f.read(), "photo.png")
    except ValueError as e:
        return error(str(e))
    if (blocked := take_picture_slot(uid)):
        return blocked
    ok, left, wait = books_per_user.take(uid)
    if not ok:
        pictures_per_user.refund(uid)
        return error(f"You've made {books_per_user.limit} books this hour. You can start another in about {minutes(wait)}.", 429)
    site_ok, _, site_wait = books_site.take("all")
    if not site_ok:
        books_per_user.refund(uid)
        pictures_per_user.refund(uid)
        return error(f"The site has hit its limit of {books_site.limit} books this hour. Try again in about {minutes(site_wait)}.", 429)
    try:
        sheet = generate(photo, hero_prompt(), uid=uid, book_id=None, action="sheet", target="sheet",
                         label="cast sheet")
    except Exception as e:
        books_per_user.refund(uid)
        books_site.refund("all")
        pictures_per_user.refund(uid)
        return api_error(e)
    book_id = db.create_book(uid, sheet, clean_details(request.form))
    return jsonify({"id": book_id, "books_left": left})


@app.patch("/api/books/<int:book_id>")
@login_required
def book_update(book_id):
    if not db.own_book(current_user_id(), book_id):
        return error("Book not found.", 404)
    db.update_details(current_user_id(), book_id, clean_details(request.get_json(silent=True) or {}))
    return jsonify({"ok": True})


@app.delete("/api/books/<int:book_id>")
@login_required
def book_delete(book_id):
    db.delete_book(current_user_id(), book_id)
    return jsonify({"ok": True})


@app.post("/api/books/<int:book_id>/pages/<int:n>")
@login_required
def page_paint(book_id, n):
    uid = current_user_id()
    p = PAGES_BY_N.get(n)
    sheet = db.get_image(uid, book_id, "sheet")
    if not p or sheet is None:
        return error("Book or page not found.", 404)
    if (blocked := take_picture_slot(uid)):
        return blocked
    try:
        img = generate(to_png(sheet, "sheet.png"), page_prompt(p), uid=uid, book_id=book_id, action="page",
                       target=n, label=f"page {n}: {p['title']}")
    except Exception as e:
        pictures_per_user.refund(uid)
        return api_error(e)
    db.save_page(uid, book_id, n, img)
    return jsonify({"ok": True, "n": n})


@app.post("/api/books/<int:book_id>/adjust")
@login_required
def adjust(book_id):
    uid = current_user_id()
    data = request.get_json(silent=True) or {}
    change = " ".join(str(data.get("change", "")).split())[:240].replace('"', "'")
    target = str(data.get("target", ""))
    if not change:
        return error("Say what to change, like “make the cow whiter”.")
    is_page = target != "sheet"
    if is_page and (not target.isdigit() or int(target) not in PAGES_BY_N):
        return error("Unknown page.")
    current = db.get_image(uid, book_id, target)
    sheet = db.get_image(uid, book_id, "sheet")
    if current is None or sheet is None:
        return error("Make that picture first.", 404)
    ok, left, wait = edits_per_user.take(uid)
    if not ok:
        return error(f"You've used your {edits_per_user.limit} changes this hour. You can make another in about "
                     f"{minutes(wait)}, or repaint the page instead.", 429)
    if (blocked := take_picture_slot(uid)):
        edits_per_user.refund(uid)
        return blocked
    try:
        img = generate([to_png(current, "image.png", 1536), to_png(sheet, "sheet.png")],
                       adjust_prompt(change, is_page), uid=uid, book_id=book_id, action="adjust",
                       target=target, label=f"{target} changed")
    except Exception as e:
        edits_per_user.refund(uid)
        pictures_per_user.refund(uid)
        return api_error(e)
    if is_page:
        db.save_page(uid, book_id, int(target), img)
    else:
        db.set_cast_sheet(uid, book_id, img)
    return jsonify({"ok": True, "edits_left": left})


@app.get("/img/<int:book_id>/<target>")
@login_required
def image(book_id, target):
    if target != "sheet" and not target.isdigit():
        abort(404)
    data = db.get_image(current_user_id(), book_id, target)
    if data is None:
        abort(404)
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/books/<int:book_id>/pdf")
@login_required
def pdf(book_id):
    uid = current_user_id()
    b = db.get_book(uid, book_id)
    if not b:
        return error("Book not found.", 404)
    if not b["child_name"]:
        return error("Add the child's name for the About Me page.")
    missing = [p["n"] for p in PAGES if p["n"] not in b["pages"]]
    if missing:
        return error(f"Paint page {missing[0]} first.")
    images = {p["n"]: db.get_image(uid, book_id, p["n"]) for p in PAGES}
    t0 = time.time()
    data = build_pdf(PAGES, images, b["child_name"], {k: b[k] for k in ("age", "likes", "about")},
                     db.get_image(uid, book_id, "sheet"))
    log.info("pdf OK user=%s book=%s ms=%d bytes=%d", uid, book_id, (time.time() - t0) * 1000, len(data))
    db.log_event(user_id=uid, book_id=book_id, action="pdf", ok=1, ms=int((time.time() - t0) * 1000))
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="JackAndTheBeanstalk.pdf"'})


@app.get("/api/activity")
@login_required
def activity():
    """Your own recent generation log (for checking that logging works)."""
    rows = db.recent_events(current_user_id())
    for r in rows:
        r["at"] = r["at"].isoformat() if r["at"] else None
    return jsonify(rows)


@app.errorhandler(413)
def too_big(_):
    return error("That request was too large. Try a smaller photo.", 413)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)), threaded=True)
