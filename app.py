"""
Storybooks starring your child: Jack and the Beanstalk, or Little Red Riding Hood. MCON 368.

  POST /api/books                 photo + story + About Me -> charges $0.99, starts the book in the background
  GET  /api/books/<id>            progress: stage, every page's status, attempts and score (polled by the page)
  GET  /api/books/<id>/pdf        the finished PDF (stored, so it downloads instantly, also on a later visit)
  /wallet                         balance, add funds (Stripe test mode), refunds, history, cost per book
  /characters                     the character bible, straight from the database
  /admin                          (owner only) draw the shared bible and pre-made scenes

Secrets (OPENAI_API_KEY, STRIPE_SECRET_KEY, GOOGLE_CLIENT_ID/SECRET, SECRET_KEY, DATABASE_URL) come from the
environment only. See stories.py for how a book is made, pipeline.py for the generation engine.
"""

import hmac
import io
import logging
import os
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

import billing
import db
import pipeline
import stories as S

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
ADMINS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def current_user_id():
    return session.get("uid")


def current_user():
    uid = current_user_id()
    return db.get_user(uid) if uid else None


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not current_user_id():
            return error("Please sign in first.", 401)
        return fn(*a, **kw)
    return wrapper


def is_admin(user):
    return bool(user) and ((user.get("email") or "").lower() in ADMINS or DEV_LOGIN)   # DEV_LOGIN: local only


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not is_admin(current_user()):
            abort(404)
        return fn(*a, **kw)
    return wrapper


# ---------------------------------------------------------------------------
# Limits
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


books_per_user = Limiter(int(os.environ.get("BOOKS_PER_HOUR", "6")))
books_site = Limiter(int(os.environ.get("SITE_BOOKS_PER_HOUR", "30")))
failed_logins = Limiter(10)   # wrong passwords per address per hour


def minutes(sec):
    m = max(1, round(sec / 60))
    return f"{m} minute{'s' if m != 1 else ''}"


def error(msg, code=400, **extra):
    return jsonify({"error": msg, **extra}), code


def clean_details(src):
    return {
        "child_name": " ".join(str(src.get("child_name", "")).split())[:40],
        "age": " ".join(str(src.get("age", "")).split())[:20],
        "likes": str(src.get("likes", "")).strip()[:300],
        "about": str(src.get("about", "")).strip()[:600],
    }


def jpeg_response(raw, cache="private, max-age=86400"):
    if raw is None:
        abort(404)
    return Response(raw, mimetype="image/jpeg", headers={"Cache-Control": cache})


def scenes_ready():
    have, _ = db.scene_status()
    return {k: all(f"{k}:{n}" in have for n in range(0, 21)) for k in S.STORY_KEYS}


# Books whose background job died with a restart: mark them failed and give the $0.99 back.
def _recover():
    for book_id in db.stale_running_books(time.time() - 600):
        b = db.get_book_internal(book_id)
        pipeline.fail_book(book_id, b["user_id"], "The server restarted while this book was being made. "
                                                  "Your $0.99 has been refunded; please make it again.")


def _drop_text_only_portraits():
    for story, key in S.TEXT_ONLY:
        db.delete_bible(story, key)


try:
    _drop_text_only_portraits()
    _recover()
except Exception as e:  # never block startup
    log.warning("recover FAIL %s", e)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    user = current_user()
    if current_user_id() and not user:          # stale cookie (e.g. database was reset)
        session.clear()
    return render_template("index.html", user=user, fake=pipeline.FAKE, dev_login=DEV_LOGIN,
                           password_login=bool(LOGIN_PASSWORD), stories=S.STORIES, ready=scenes_ready(),
                           balance=billing.money(db.balance(user["id"])) if user else None,
                           admin=is_admin(user), price=billing.money(billing.BOOK_PRICE),
                           hero_pages={k: len(v) for k, v in S.HERO_PAGES.items()})


@app.get("/wallet")
def wallet_page():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    note, bad = None, False
    if request.args.get("paid"):
        try:
            got = billing.confirm_checkout(user["id"], request.args["paid"])
            note = f"Added {billing.money(got)} to your balance." if got else "That payment hasn't gone through."
            bad = not got
        except Exception as e:
            note, bad = f"Couldn't confirm the payment with Stripe: {str(e)[:120]}", True
    elif request.args.get("cancelled"):
        note = "Payment cancelled. Nothing was charged."
    try:                                   # recover any paid checkout that wasn't credited
        found = billing.reconcile(user["id"], request.host_url.rstrip("/"))
        if found:
            note = f"Added {billing.money(found)} to your balance from a payment that hadn't been credited yet."
            bad = False
    except Exception as e:
        log.warning("reconcile FAIL %s", str(e)[:200])
    return render_template("wallet.html", user=user, note=note, bad=bad, amounts=billing.AMOUNTS,
                           money=billing.money, fake_stripe=billing.FAKE, admin=is_admin(user),
                           price=billing.money(billing.BOOK_PRICE), balance=billing.money(db.balance(user["id"])))


@app.get("/characters")
def characters_page():
    rows = {}
    for k in S.STORY_KEYS:
        have = {r["key"]: r for r in db.get_bible(k)}
        rows[k] = [{"key": key, "name": name, "description": desc, "has": key in have,
                    "note": S.TEXT_ONLY_NOTE if S.text_only(k, key) else ("Not drawn yet." if key not in have else "")}
                   for key, (name, desc) in S.BIBLE[k].items()]
    return render_template("characters.html", user=current_user(), stories=S.STORIES, rows=rows,
                           hero=S.HERO, balance=billing.money(db.balance(current_user_id())) if current_user_id() else None)


@app.get("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", user=current_user(), stories=S.STORIES, bible=S.BIBLE,
                           text_only=[f"{s}:{k}" for s, k in S.TEXT_ONLY],
                           balance=billing.money(db.balance(current_user_id())))


@app.get("/privacy")
def privacy():
    return render_template("privacy.html", updated="November 8, 2026", contact=os.environ.get("CONTACT_EMAIL", ""))


@app.get("/font/young-serif.ttf")
def font():
    with open(os.path.join(os.path.dirname(__file__), "fonts", "YoungSerif-Regular.ttf"), "rb") as fh:
        return Response(fh.read(), mimetype="font/ttf", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/healthz")
def health():
    return "ok"


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------
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
# Books
# ---------------------------------------------------------------------------
def book_json(b):
    out = {k: b[k] for k in ("id", "story", "child_name", "age", "likes", "about", "status", "stage", "error",
                             "has_hero", "has_pdf", "hero_attempts", "hero_score", "hero_passed")}
    out["title"] = S.STORIES[b["story"]]["title"]
    end = b["done_at"] or time.time()
    out["elapsed"] = round(end - b["started_at"], 1) if b["started_at"] else None
    pages = []
    for p in b["pages"]:
        t = S.page_by_n(b["story"], p["n"])
        pages.append({**p, "text": t["text"], "premade": not t["hero"], "layout": t["layout"],
                      "cover": p["n"] == 0})
    out["pages"] = pages
    done = sum(1 for p in pages if p["status"] == "done")
    out["done_pages"] = done
    if b["status"] == "running" and pages and b["stage"] == "Painting the pages":
        painting = [p for p in pages if p["status"] in ("painting", "checking")]
        retry = [p for p in painting if (p["attempts"] or 0) > 1]
        out["stage"] = (f"Painting and checking pages: {done} of {len(pages)} done"
                        + (f", repainting {len(retry)}" if retry else ""))
    return out


@app.get("/api/books")
@login_required
def books_list():
    rows = db.list_books(current_user_id())
    for r in rows:
        r["title"] = S.STORIES[r["story"]]["title"]
        r["seconds"] = round(r["done_at"] - r["started_at"]) if r["done_at"] and r["started_at"] else None
        r["created_at"] = r["created_at"].isoformat() if r["created_at"] else None
    return jsonify(rows)


@app.get("/api/books/<int:book_id>")
@login_required
def book_get(book_id):
    b = db.get_book(current_user_id(), book_id)
    if not b:
        return error("Book not found.", 404)
    return jsonify(book_json(b))


@app.post("/api/books")
@login_required
def book_create():
    t0 = time.time()                      # the clock starts when the photo arrives
    uid = current_user_id()
    story = request.form.get("story", "")
    if story not in S.STORIES:
        return error("Choose a story first.")
    if not scenes_ready().get(story):
        return error("This story's pictures are still being prepared. Please try the other story, or come back soon.", 503)
    f = request.files.get("photo")
    if not f:
        return error("Add a photo first.")
    try:
        photo = pipeline.to_png(f.read(), 1024)
    except Exception:
        return error("That file isn't a readable image. Use a JPG, PNG or WEBP photo.")
    details = clean_details(request.form)
    if db.balance(uid) < billing.BOOK_PRICE:
        return error(f"A book costs {billing.money(billing.BOOK_PRICE)} and your balance is "
                     f"{billing.money(db.balance(uid))}. Add funds to make this book.", 402, need_funds=True)
    ok, _, wait = books_per_user.take(uid)
    if not ok:
        return error(f"You've made {books_per_user.limit} books this hour. Try again in about {minutes(wait)}.", 429)
    if not books_site.take("site")[0]:
        books_per_user.refund(uid)
        return error("The site is very busy right now. Please try again in a little while.", 429)

    book_id = db.create_book(uid, story, details, t0)
    charge = billing.charge_book(uid, book_id, S.STORIES[story]["title"])
    if charge is None:                    # balance changed in the meantime: nothing taken, nothing made
        db.delete_book(uid, book_id)
        books_per_user.refund(uid)
        return error(f"Your balance is {billing.money(db.balance(uid))}, short of the "
                     f"{billing.money(billing.BOOK_PRICE)} a book costs. Add funds to continue.", 402, need_funds=True)
    db.update_book(book_id, charge_id=charge)
    pipeline.start_book(book_id, uid, photo)
    log.info("book %s started story=%s user=%s", book_id, story, uid)
    return jsonify({"id": book_id, "balance": billing.money(db.balance(uid))})


@app.delete("/api/books/<int:book_id>")
@login_required
def book_delete(book_id):
    if pipeline.is_running(book_id):
        return error("This book is still being made. Delete it once it's finished.", 409)
    if not db.delete_book(current_user_id(), book_id):
        return error("Book not found.", 404)
    return jsonify({"ok": True})


@app.get("/api/books/<int:book_id>/thumb/<int:n>")
@login_required
def page_thumb(book_id, n):
    return jpeg_response(db.page_image(current_user_id(), book_id, n, thumb=True), "private, no-cache")


@app.get("/api/books/<int:book_id>/page/<int:n>")
@login_required
def page_full(book_id, n):
    return jpeg_response(db.page_image(current_user_id(), book_id, n), "private, no-cache")


@app.get("/api/books/<int:book_id>/hero")
@login_required
def hero_img(book_id):
    return jpeg_response(db.get_blob(current_user_id(), book_id, "hero"))


@app.get("/api/books/<int:book_id>/pdf")
@login_required
def pdf(book_id):
    b = db.get_book(current_user_id(), book_id)
    raw = db.get_blob(current_user_id(), book_id, "pdf") if b else None
    if raw is None:
        return error("That book's PDF isn't ready.", 404)
    name = ("".join(ch for ch in (b["child_name"] or "") if ch.isalnum()) or "My") + "-" + \
        S.STORIES[b["story"]]["title"].replace(" ", "")
    return Response(raw, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------
@app.get("/api/wallet")
@login_required
def wallet_api():
    uid = current_user_id()
    hist = db.history(uid)
    refunds = db.list_refunds(uid)
    out_hist = []
    for r in hist:
        row = {k: r[k] for k in ("id", "kind", "amount_cents", "balance_cents", "book_id", "note")}
        row["at"] = r["at"].isoformat() if r["at"] else None
        row["amount"] = billing.money(r["amount_cents"])
        row["balance"] = billing.money(r["balance_cents"])
        row["refundable"] = billing.money(billing.refundable(uid, r)) if r["kind"] in ("deposit", "book") else None
        row["can_refund"] = r["kind"] in ("deposit", "book") and billing.refundable(uid, r) > 0
        out_hist.append(row)
    out_ref = [{"id": r["id"], "kind": r["kind"], "ledger_id": r["ledger_id"], "amount": billing.money(r["amount_cents"]),
                "status": r["status"], "reason": r["reason"], "error": r["error"], "stripe_ref": r["stripe_ref"],
                "requested_at": r["requested_at"].isoformat() if r["requested_at"] else None,
                "processed_at": r["processed_at"].isoformat() if r["processed_at"] else None} for r in refunds]
    rep = db.cost_report()
    return jsonify({"balance": billing.money(db.balance(uid)), "balance_cents": db.balance(uid),
                    "history": out_hist, "refunds": out_ref, "cost": rep, "price": billing.BOOK_PRICE / 100})


@app.post("/billing/checkout")
@login_required
def checkout():
    user = current_user()
    try:
        amount = int(request.form.get("amount", "0"))
        url = billing.start_checkout(user, amount, request.host_url.rstrip("/"))
    except ValueError as e:
        return redirect(url_for("wallet_page", cancelled=1, err=str(e)))
    except Exception as e:
        log.warning("checkout FAIL %s", e)
        return render_template("wallet.html", user=user, note=f"Stripe couldn't start the payment: {str(e)[:150]}",
                               bad=True, amounts=billing.AMOUNTS, money=billing.money, fake_stripe=billing.FAKE,
                               admin=is_admin(user), price=billing.money(billing.BOOK_PRICE),
                               balance=billing.money(db.balance(user["id"]))), 502
    return redirect(url, code=303)


@app.route("/billing/fake-checkout", methods=["GET", "POST"])
@login_required
def fake_checkout():
    if not billing.FAKE:
        abort(404)
    sid = request.values.get("session_id", "")
    if request.method == "POST":
        billing.fake_pay(sid)
        return redirect(url_for("wallet_page", paid=sid))
    s = billing._fake_sessions.get(sid)
    if not s:
        abort(404)
    return render_template("fake_checkout.html", sid=sid, amount=billing.money(s["amount"]))


@app.post("/api/refunds")
@login_required
def refund_request():
    data = request.get_json(silent=True) or {}
    try:
        rid = billing.request_refund(current_user_id(), int(data.get("ledger_id", 0)), str(data.get("reason", "")))
    except ValueError as e:
        return error(str(e))
    return jsonify({"id": rid})


@app.post("/api/refunds/<int:refund_id>/process")
@login_required
def refund_process(refund_id):
    try:
        amount = billing.process_refund(current_user_id(), refund_id)
    except ValueError as e:
        return error(str(e))
    return jsonify({"ok": True, "amount": billing.money(amount), "balance": billing.money(db.balance(current_user_id()))})


# ---------------------------------------------------------------------------
# Character bible and pre-made scenes (images are shared art, not personal data)
# ---------------------------------------------------------------------------
@app.get("/bible/<story>/<key>.jpg")
def bible_img(story, key):
    return jpeg_response(db.bible_image(story, key), "public, max-age=3600")


@app.get("/scene/<story>/<int:n>.jpg")
def scene_img(story, n):
    w = request.args.get("w", type=int)
    if w:                                   # a sharp copy at the size the page shows it (e.g. the story picker)
        w = max(200, min(1536, w))
        key = (story, n, w)
        if key not in _sized:
            raw, _ = db.get_scene(story, n)
            if raw is None:
                abort(404)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((w, w))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85, optimize=True)
            _sized[key] = buf.getvalue()
        return jpeg_response(_sized[key], "public, max-age=600")
    raw, _ = db.get_scene(story, n, thumb=request.args.get("full") != "1")
    return jpeg_response(raw, "public, max-age=3600")


_sized = {}   # resized scene images, cleared whenever the shared art is redrawn


@app.get("/api/bible")
def bible_api():
    """The character bible as stored in the database."""
    out = {}
    for k in S.STORY_KEYS:
        have = {r["key"] for r in db.get_bible(k)}
        out[k] = [{"key": key, "name": name, "description": desc,
                   "image": url_for("bible_img", story=k, key=key) if key in have else None,
                   "note": S.TEXT_ONLY_NOTE if S.text_only(k, key) else None}
                  for key, (name, desc) in S.BIBLE[k].items()]
    return jsonify(out)


@app.get("/api/admin/status")
@admin_required
def admin_status():
    have_scenes, have_bible = db.scene_status()
    st = pipeline.pregen_state
    return jsonify({"running": st["running"], "done": st["done"], "total": st["total"], "log": list(st["log"])[:60],
                    "scenes": have_scenes, "bible": list(have_bible), "cost": db.cost_report(),
                    "model": pipeline.IMAGE_MODEL, "quality": pipeline.QUALITY, "ipm": pipeline.IPM,
                    "failures": db.recent_failures()})


@app.post("/api/admin/pregen")
@admin_required
def admin_pregen():
    d = request.get_json(silent=True) or {}
    story = d.get("story")
    if story not in S.STORIES:
        return error("Unknown story.")
    only = d.get("only")
    if isinstance(only, list):
        only = [int(x) for x in only]
    _sized.clear()
    if not pipeline.start_pregen(story, only, bool(d.get("redo"))):
        return error("Already running.", 409)
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_big(_):
    return error("That photo is too large. Try a smaller one (under 20 MB).", 413)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)), threaded=True)
