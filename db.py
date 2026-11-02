"""
Storage: each signed-in user's books persist between visits.

DATABASE_URL (set on Render) points at Postgres. Without it, a local SQLite file is used for testing.
Images are stored as JPEG bytes in the database: a 3-page book is ~2 MB, so a free 1 GB database
holds hundreds of books. The uploaded photo itself is never stored.
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (Column, DateTime, ForeignKey, Integer, LargeBinary, MetaData, String, Table, Text,
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
# Books (every query is scoped to the owner, so nobody can read someone else's book)
# ---------------------------------------------------------------------------
DETAIL_FIELDS = ("child_name", "age", "likes", "about")


def create_book(user_id, cast_sheet, details):
    vals = {k: details.get(k, "") for k in DETAIL_FIELDS}
    with engine.begin() as c:
        return c.execute(insert(books).values(user_id=user_id, cast_sheet=cast_sheet, **vals)
                         ).inserted_primary_key[0]


def own_book(user_id, book_id):
    with engine.connect() as c:
        r = c.execute(select(books.c.id).where(books.c.id == book_id, books.c.user_id == user_id)).first()
        return r is not None


def update_details(user_id, book_id, details):
    vals = {k: details[k] for k in DETAIL_FIELDS if k in details}
    if not vals:
        return
    with engine.begin() as c:
        c.execute(update(books).where(books.c.id == book_id, books.c.user_id == user_id)
                  .values(updated_at=now(), **vals))


def set_cast_sheet(user_id, book_id, jpeg):
    with engine.begin() as c:
        c.execute(update(books).where(books.c.id == book_id, books.c.user_id == user_id)
                  .values(cast_sheet=jpeg, updated_at=now()))


def save_page(user_id, book_id, n, jpeg):
    if not own_book(user_id, book_id):
        raise PermissionError
    with engine.begin() as c:
        c.execute(delete(pages).where(pages.c.book_id == book_id, pages.c.n == n))
        c.execute(insert(pages).values(book_id=book_id, n=n, image=jpeg))
        c.execute(update(books).where(books.c.id == book_id).values(updated_at=now()))


def list_books(user_id):
    with engine.connect() as c:
        rows = c.execute(
            select(books.c.id, books.c.child_name, books.c.created_at, books.c.updated_at,
                   func.count(pages.c.n).label("page_count"))
            .select_from(books.outerjoin(pages, pages.c.book_id == books.c.id))
            .where(books.c.user_id == user_id)
            .group_by(books.c.id).order_by(books.c.updated_at.desc())
        ).all()
        return [dict(r._mapping) for r in rows]


def get_book(user_id, book_id):
    with engine.connect() as c:
        b = c.execute(select(*[books.c[k] for k in ("id", *DETAIL_FIELDS, "updated_at")])
                      .where(books.c.id == book_id, books.c.user_id == user_id)).first()
        if not b:
            return None
        ns = [r.n for r in c.execute(select(pages.c.n).where(pages.c.book_id == book_id))]
        return {**dict(b._mapping), "pages": sorted(ns)}


def get_image(user_id, book_id, target):
    """target: 'sheet' or a page number."""
    with engine.connect() as c:
        if target == "sheet":
            r = c.execute(select(books.c.cast_sheet)
                          .where(books.c.id == book_id, books.c.user_id == user_id)).first()
            return r[0] if r else None
        r = c.execute(select(pages.c.image).select_from(pages.join(books, books.c.id == pages.c.book_id))
                      .where(pages.c.book_id == book_id, pages.c.n == int(target),
                             books.c.user_id == user_id)).first()
        return r[0] if r else None


def delete_book(user_id, book_id):
    with engine.begin() as c:
        c.execute(delete(pages).where(pages.c.book_id.in_(
            select(books.c.id).where(books.c.id == book_id, books.c.user_id == user_id))))
        c.execute(delete(books).where(books.c.id == book_id, books.c.user_id == user_id))


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
