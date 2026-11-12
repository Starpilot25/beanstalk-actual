"""
Storage: users, books (v2: 20 pages), the character bible and pre-made scenes, money, and the API cost log.

DATABASE_URL (set on Render) points at Postgres. Without it, a local SQLite file is used for testing.
Images are stored as JPEG bytes in the database: a 3-page book is ~2 MB, so a free 1 GB database
holds hundreds of books. The uploaded photo itself is never stored.
"""

import os
from datetime import datetime, timezone

import json
import threading
import time

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, LargeBinary, MetaData, String, Table, Text,
                        create_engine, delete, func, insert, select, update)

url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if url.startswith("postgres://"):            # Render/Heroku style -> SQLAlchemy + psycopg 3
    url = "postgresql+psycopg://" + url[len("postgres://"):]
elif url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]

engine = create_engine(url, pool_pre_ping=True, future=True)
meta = MetaData()


def now():
    return datetime.now(timezone.utc)


users = Table(
    "users", meta,
    Column("id", Integer, primary_key=True),
    Column("google_sub", String(64), unique=True, nullable=False),   # Google's stable user id
    Column("email", String(320), nullable=False),
    Column("name", String(200)),
    Column("picture", Text),
    Column("created_at", DateTime(timezone=True), default=now),
    Column("last_login", DateTime(timezone=True), default=now),
)

books = Table(
    "books", meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
    Column("child_name", String(40), default=""),
    Column("age", String(20), default=""),
    Column("likes", String(300), default=""),
    Column("about", String(600), default=""),
    Column("cast_sheet", LargeBinary),          # JPEG
    Column("created_at", DateTime(timezone=True), default=now),
    Column("updated_at", DateTime(timezone=True), default=now),
)

pages = Table(
    "pages", meta,
    Column("book_id", Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("image", LargeBinary, nullable=False),  # JPEG
    Column("updated_at", DateTime(timezone=True), default=now),
)

# Generation log: one row per image request (also printed to the server log).
events = Table(
    "events", meta,
    Column("id", Integer, primary_key=True),
    Column("at", DateTime(timezone=True), default=now, index=True),
    Column("user_id", Integer, index=True),
    Column("book_id", Integer),
    Column("action", String(30)),        # sheet | page | adjust | pdf | login
    Column("target", String(20)),        # "sheet" or page number
    Column("model", String(60)),
    Column("ms", Integer),
    Column("ok", Integer),
    Column("detail", String(300)),
)

# --- v2 (20-page books). The tables above ("books", "pages") hold the old 3-page drafts and are no longer used.
storybooks = Table(
    "storybooks", meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
    Column("story", String(20), nullable=False),        # jack | red
    Column("child_name", String(40), default=""),
    Column("age", String(20), default=""),
    Column("likes", String(300), default=""),
    Column("about", String(600), default=""),
    Column("hero", LargeBinary),                        # the hero sheet (JPEG): this book's entry in the bible
    Column("status", String(20), default="new"),        # new | running | done | failed
    Column("stage", String(120), default=""),           # what the progress bar says
    Column("started_at", Float),                        # unix seconds: photo submitted
    Column("done_at", Float),                           # unix seconds: PDF ready
    Column("pdf", LargeBinary),
    Column("error", String(400)),
    Column("charge_id", Integer),                       # ledger row of the $0.99
    Column("created_at", DateTime(timezone=True), default=now),
)

book_pages = Table(
    "book_pages", meta,
    Column("book_id", Integer, ForeignKey("storybooks.id", ondelete="CASCADE"), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("status", String(20), default="waiting"),    # waiting | painting | checking | done | failed
    Column("attempts", Integer, default=0),
    Column("score", Float),
    Column("zone", String(20)),                         # where the words go: top | middle | bottom | below
    Column("issues", Text),
    Column("image", LargeBinary),
    Column("thumb", LargeBinary),
    Column("updated_at", Float),
)

page_attempts = Table(            # every generation of every page, so "best of three" is auditable
    "page_attempts", meta,
    Column("id", Integer, primary_key=True),
    Column("book_id", Integer, index=True),
    Column("n", Integer),
    Column("attempt", Integer),
    Column("score", Float),
    Column("passed", Integer),
    Column("analysis", Text),
    Column("image", LargeBinary),
    Column("at", Float),
)

bible = Table(                     # the character bible: one row per supporting character per story
    "bible", meta,
    Column("story", String(20), primary_key=True),
    Column("key", String(30), primary_key=True),
    Column("name", String(60)),
    Column("description", Text),
    Column("image", LargeBinary),
    Column("updated_at", Float),
)

scenes = Table(                    # pre-generated scenes, shared by every book
    "scenes", meta,
    Column("story", String(20), primary_key=True),
    Column("n", Integer, primary_key=True),
    Column("image", LargeBinary),
    Column("thumb", LargeBinary),
    Column("attempts", Integer, default=0),
    Column("score", Float),
    Column("analysis", Text),
    Column("updated_at", Float),
)

ledger = Table(                    # every credit and debit; the balance is the sum
    "ledger", meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
    Column("at", DateTime(timezone=True), default=now),
    Column("kind", String(20)),          # deposit | book | book_refund | card_refund | reversal
    Column("amount_cents", Integer),     # + credit, - debit
    Column("balance_cents", Integer),    # balance after this row
    Column("book_id", Integer),
    Column("ref", String(120), unique=True),   # Stripe checkout session / refund id (idempotency)
    Column("note", String(300)),
)

refunds = Table(
    "refunds", meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, index=True, nullable=False),
    Column("kind", String(10)),          # book (back to balance) | card (back to the card via Stripe)
    Column("ledger_id", Integer),        # the charge or deposit being refunded
    Column("amount_cents", Integer),
    Column("reason", String(300)),
    Column("status", String(20), default="requested"),   # requested | processed | failed
    Column("requested_at", DateTime(timezone=True), default=now),
    Column("processed_at", DateTime(timezone=True)),
    Column("stripe_ref", String(120)),
    Column("error", String(300)),
)

api_calls = Table(                 # what every API call cost us
    "api_calls", meta,
    Column("id", Integer, primary_key=True),
    Column("at", Float, index=True),
    Column("user_id", Integer),
    Column("book_id", Integer, index=True),
    Column("purpose", String(20)),       # hero | page | retry | analysis | bible | scene
    Column("model", String(60)),
    Column("ms", Integer),
    Column("ok", Integer),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost_usd", Float),
    Column("detail", String(300)),
)

meta.create_all(engine)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def upsert_user(sub, email, name, picture):
    with engine.begin() as c:
        row = c.execute(select(users.c.id).where(users.c.google_sub == sub)).first()
        if row:
            c.execute(update(users).where(users.c.id == row.id)
                      .values(email=email, name=name, picture=picture, last_login=now()))
            return row.id
        return c.execute(insert(users).values(google_sub=sub, email=email, name=name, picture=picture)
                         ).inserted_primary_key[0]


def get_user(user_id):
    with engine.connect() as c:
        r = c.execute(select(users.c.id, users.c.email, users.c.name, users.c.picture)
                      .where(users.c.id == user_id)).first()
        return dict(r._mapping) if r else None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log_event(**kw):
    try:
        with engine.begin() as c:
            c.execute(insert(events).values(**kw))
    except Exception:   # logging must never break a request
        pass


def recent_events(user_id, limit=20):
    with engine.connect() as c:
        rows = c.execute(select(events).where(events.c.user_id == user_id)
                         .order_by(events.c.at.desc()).limit(limit)).all()
        return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Books v2 (every user-facing query is scoped to the owner)
# ---------------------------------------------------------------------------
DETAIL_FIELDS = ("child_name", "age", "likes", "about")
BOOK_COLS = ("id", "story", *DETAIL_FIELDS, "status", "stage", "started_at", "done_at", "error", "charge_id",
             "created_at")


def create_book(user_id, story, details, started_at):
    vals = {k: (details.get(k) or "")[:{"child_name": 40, "age": 20, "likes": 300, "about": 600}[k]]
            for k in DETAIL_FIELDS}
    with engine.begin() as c:
        return c.execute(insert(storybooks).values(user_id=user_id, story=story, status="running",
                                                   stage="Starting", started_at=started_at, **vals)
                         ).inserted_primary_key[0]


def update_book(book_id, **vals):
    with engine.begin() as c:
        c.execute(update(storybooks).where(storybooks.c.id == book_id).values(**vals))


def get_book(user_id, book_id):
    with engine.connect() as c:
        b = c.execute(select(*[storybooks.c[k] for k in BOOK_COLS])
                      .where(storybooks.c.id == book_id, storybooks.c.user_id == user_id)).first()
        if not b:
            return None
        ps = c.execute(select(book_pages.c.n, book_pages.c.status, book_pages.c.attempts, book_pages.c.score,
                              book_pages.c.zone, book_pages.c.issues, book_pages.c.updated_at)
                       .where(book_pages.c.book_id == book_id).order_by(book_pages.c.n)).all()
        has = c.execute(select(storybooks.c.hero.isnot(None), storybooks.c.pdf.isnot(None))
                        .where(storybooks.c.id == book_id)).first()
        hero_tries = c.execute(select(page_attempts.c.attempt, page_attempts.c.score, page_attempts.c.passed)
                               .where(page_attempts.c.book_id == book_id, page_attempts.c.n == -1)
                               .order_by(page_attempts.c.attempt)).all()
        return {**dict(b._mapping), "has_hero": bool(has[0]), "has_pdf": bool(has[1]),
                "hero_attempts": len(hero_tries),
                "hero_score": max((r.score for r in hero_tries), default=None),
                "hero_passed": any(r.passed for r in hero_tries),
                "pages": [dict(r._mapping) for r in ps]}


def list_books(user_id):
    with engine.connect() as c:
        rows = c.execute(select(storybooks.c.id, storybooks.c.story, storybooks.c.child_name, storybooks.c.status,
                                storybooks.c.started_at, storybooks.c.done_at, storybooks.c.created_at,
                                storybooks.c.pdf.isnot(None).label("has_pdf"))
                         .where(storybooks.c.user_id == user_id).order_by(storybooks.c.id.desc())).all()
        return [dict(r._mapping) for r in rows]


def get_blob(user_id, book_id, what):
    """what: hero | pdf. Owner only."""
    with engine.connect() as c:
        r = c.execute(select(storybooks.c[what]).where(storybooks.c.id == book_id,
                                                       storybooks.c.user_id == user_id)).first()
        return r[0] if r else None


def get_book_internal(book_id):
    with engine.connect() as c:
        r = c.execute(select(storybooks).where(storybooks.c.id == book_id)).first()
        return dict(r._mapping) if r else None


def init_pages(book_id, ns):
    with engine.begin() as c:
        c.execute(delete(book_pages).where(book_pages.c.book_id == book_id))
        for n in ns:
            c.execute(insert(book_pages).values(book_id=book_id, n=n, status="waiting", attempts=0,
                                                updated_at=time.time()))


def set_page(book_id, n, **vals):
    vals["updated_at"] = time.time()
    with engine.begin() as c:
        c.execute(update(book_pages).where(book_pages.c.book_id == book_id, book_pages.c.n == n).values(**vals))


def page_image(user_id, book_id, n, thumb=False):
    col = book_pages.c.thumb if thumb else book_pages.c.image
    with engine.connect() as c:
        r = c.execute(select(col).select_from(book_pages.join(storybooks, storybooks.c.id == book_pages.c.book_id))
                      .where(book_pages.c.book_id == book_id, book_pages.c.n == n,
                             storybooks.c.user_id == user_id)).first()
        return r[0] if r else None


def page_images_internal(book_id):
    with engine.connect() as c:
        rows = c.execute(select(book_pages.c.n, book_pages.c.image, book_pages.c.zone)
                         .where(book_pages.c.book_id == book_id)).all()
        return {r.n: (r.image, r.zone) for r in rows}


def add_attempt(book_id, n, attempt, score, passed, analysis, image):
    with engine.begin() as c:
        c.execute(insert(page_attempts).values(book_id=book_id, n=n, attempt=attempt, score=score,
                                               passed=int(passed), analysis=json.dumps(analysis), image=image,
                                               at=time.time()))


def delete_book(user_id, book_id):
    with engine.begin() as c:
        if not c.execute(select(storybooks.c.id).where(storybooks.c.id == book_id,
                                                       storybooks.c.user_id == user_id)).first():
            return False
        c.execute(delete(book_pages).where(book_pages.c.book_id == book_id))
        c.execute(delete(page_attempts).where(page_attempts.c.book_id == book_id))
        c.execute(delete(storybooks).where(storybooks.c.id == book_id))
        return True


def stale_running_books(older_than):
    with engine.connect() as c:
        return [r.id for r in c.execute(select(storybooks.c.id).where(storybooks.c.status == "running",
                                                                      storybooks.c.started_at < older_than))]


# ---------------------------------------------------------------------------
# Character bible and pre-made scenes
# ---------------------------------------------------------------------------
def save_bible(story, key, name, description, image):
    with engine.begin() as c:
        c.execute(delete(bible).where(bible.c.story == story, bible.c.key == key))
        c.execute(insert(bible).values(story=story, key=key, name=name, description=description, image=image,
                                       updated_at=time.time()))


def delete_bible(story, key):
    with engine.begin() as c:
        c.execute(delete(bible).where(bible.c.story == story, bible.c.key == key))


def get_bible(story, key=None, with_images=False):
    cols = [bible.c.story, bible.c.key, bible.c.name, bible.c.description, bible.c.updated_at]
    if with_images:
        cols.append(bible.c.image)
    q = select(*cols).where(bible.c.story == story)
    if key:
        q = q.where(bible.c.key == key)
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(q)]


def bible_image(story, key):
    with engine.connect() as c:
        r = c.execute(select(bible.c.image).where(bible.c.story == story, bible.c.key == key)).first()
        return r[0] if r else None


def save_scene(story, n, image, thumb, attempts, score, analysis):
    with engine.begin() as c:
        c.execute(delete(scenes).where(scenes.c.story == story, scenes.c.n == n))
        c.execute(insert(scenes).values(story=story, n=n, image=image, thumb=thumb, attempts=attempts, score=score,
                                        analysis=json.dumps(analysis), updated_at=time.time()))


def get_scene(story, n, thumb=False):
    with engine.connect() as c:
        r = c.execute(select(scenes.c.thumb if thumb else scenes.c.image, scenes.c.analysis)
                      .where(scenes.c.story == story, scenes.c.n == n)).first()
        return (r[0], json.loads(r[1] or "{}")) if r else (None, None)


def scene_status():
    with engine.connect() as c:
        rows = c.execute(select(scenes.c.story, scenes.c.n, scenes.c.attempts, scenes.c.score, scenes.c.analysis))
        s = {f"{r.story}:{r.n}": dict(r._mapping) for r in rows}
        b = {f"{r.story}:{r.key}": True for r in c.execute(select(bible.c.story, bible.c.key)
                                                            .where(bible.c.image.isnot(None)))}
        return s, b


# ---------------------------------------------------------------------------
# Money. One lock + one transaction per change, so the balance can never go negative.
# ---------------------------------------------------------------------------
_money = threading.Lock()


def balance(user_id, c=None):
    q = select(func.coalesce(func.sum(ledger.c.amount_cents), 0)).where(ledger.c.user_id == user_id)
    if c is not None:
        return int(c.execute(q).scalar())
    with engine.connect() as cc:
        return int(cc.execute(q).scalar())


def post(user_id, kind, amount_cents, note, book_id=None, ref=None, need_funds=False):
    """Add one ledger row. need_funds: refuse (return None) if it would take the balance below zero.
    A repeated ref (same Stripe session or refund) is ignored and returns the existing row id."""
    with _money, engine.begin() as c:
        if ref:
            r = c.execute(select(ledger.c.id).where(ledger.c.ref == ref)).first()
            if r:
                return r.id
        c.execute(select(users.c.id).where(users.c.id == user_id).with_for_update())
        bal = balance(user_id, c)
        if need_funds and bal + amount_cents < 0:
            return None
        return c.execute(insert(ledger).values(user_id=user_id, kind=kind, amount_cents=amount_cents,
                                               balance_cents=bal + amount_cents, book_id=book_id, ref=ref,
                                               note=note)).inserted_primary_key[0]


def history(user_id):
    with engine.connect() as c:
        rows = c.execute(select(ledger).where(ledger.c.user_id == user_id).order_by(ledger.c.id.desc())).all()
        return [dict(r._mapping) for r in rows]


def ledger_row(user_id, ledger_id):
    with engine.connect() as c:
        r = c.execute(select(ledger).where(ledger.c.id == ledger_id, ledger.c.user_id == user_id)).first()
        return dict(r._mapping) if r else None


def refunded_cents(ledger_id):
    """How much of a charge or deposit has already been refunded or is waiting to be."""
    with engine.connect() as c:
        return int(c.execute(select(func.coalesce(func.sum(refunds.c.amount_cents), 0))
                             .where(refunds.c.ledger_id == ledger_id,
                                    refunds.c.status.in_(("requested", "processed")))).scalar())


def add_refund(user_id, kind, ledger_id, amount_cents, reason):
    with engine.begin() as c:
        return c.execute(insert(refunds).values(user_id=user_id, kind=kind, ledger_id=ledger_id,
                                                amount_cents=amount_cents, reason=reason[:300])
                         ).inserted_primary_key[0]


def get_refund(user_id, refund_id):
    with engine.connect() as c:
        r = c.execute(select(refunds).where(refunds.c.id == refund_id, refunds.c.user_id == user_id)).first()
        return dict(r._mapping) if r else None


def update_refund(refund_id, **vals):
    with engine.begin() as c:
        c.execute(update(refunds).where(refunds.c.id == refund_id).values(**vals))


def list_refunds(user_id):
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(select(refunds).where(refunds.c.user_id == user_id)
                                                    .order_by(refunds.c.id.desc()))]


# ---------------------------------------------------------------------------
# API cost log
# ---------------------------------------------------------------------------
def log_call(**kw):
    try:
        with engine.begin() as c:
            c.execute(insert(api_calls).values(at=time.time(), **kw))
    except Exception:
        pass


def cost_report():
    """Average cost per finished book, split by kind of call; plus the one-time cost of the shared art."""
    with engine.connect() as c:
        done = [r.id for r in c.execute(select(storybooks.c.id).where(storybooks.c.status == "done"))]
        per = {}
        if done:
            rows = c.execute(select(api_calls.c.book_id, api_calls.c.purpose,
                                    func.sum(api_calls.c.cost_usd), func.count())
                             .where(api_calls.c.book_id.in_(done))
                             .group_by(api_calls.c.book_id, api_calls.c.purpose)).all()
            for b, purpose, cost, n in rows:
                d = per.setdefault(b, {})
                d[purpose] = (d.get(purpose, (0, 0))[0] + (cost or 0), d.get(purpose, (0, 0))[1] + n)
        shared = c.execute(select(func.coalesce(func.sum(api_calls.c.cost_usd), 0), func.count())
                           .where(api_calls.c.purpose.in_(("bible", "scene", "scene_check")))).first()
        times = [r.done_at - r.started_at for r in c.execute(
            select(storybooks.c.started_at, storybooks.c.done_at).where(storybooks.c.status == "done"))
            if r.done_at and r.started_at]
    books_n = len(per)
    kinds = {}
    for d in per.values():
        for k, (cost, n) in d.items():
            kinds.setdefault(k, [0.0, 0])
            kinds[k][0] += cost
            kinds[k][1] += n
    total = sum(v[0] for v in kinds.values())
    return {
        "books": books_n,
        "avg_cost": (total / books_n) if books_n else None,
        "by_kind": {k: {"avg_cost": v[0] / books_n, "avg_calls": v[1] / books_n} for k, v in kinds.items()}
        if books_n else {},
        "shared_cost": float(shared[0] or 0), "shared_calls": int(shared[1] or 0),
        "avg_seconds": (sum(times) / len(times)) if times else None,
        "fastest_seconds": min(times) if times else None,
    }


def book_cost(book_id):
    with engine.connect() as c:
        r = c.execute(select(func.coalesce(func.sum(api_calls.c.cost_usd), 0), func.count())
                      .where(api_calls.c.book_id == book_id)).first()
        return float(r[0]), int(r[1])


def recent_failures(limit=12):
    with engine.connect() as c:
        rows = c.execute(select(api_calls.c.at, api_calls.c.purpose, api_calls.c.model, api_calls.c.detail)
                         .where(api_calls.c.ok == 0).order_by(api_calls.c.id.desc()).limit(limit)).all()
        return [f"{time.strftime('%H:%M:%S', time.localtime(r.at))} {r.purpose} {r.model}: {r.detail}" for r in rows]
