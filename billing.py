"""
Money, in Stripe test mode. No real money moves.

- Add funds: a Stripe Checkout page (test card 4242 4242 4242 4242). When Stripe sends the customer back we
  look the session up on Stripe's side and credit the balance once (the session id is the ledger's unique ref).
- A book costs $0.99, taken from the balance when it starts; refused if the balance is short.
- Refunds are requested, then processed:
    book refund - a book's $0.99 goes back to the balance
    card refund - unused balance goes back to the card the deposit came from, through Stripe's Refund API
- Every change is one ledger row with its cause; the balance is the sum of the rows.

STRIPE_SECRET_KEY comes from the environment only (Render -> Environment, or .env locally). Never commit it.
Without a key (or with STRIPE_FAKE=1) a built-in pretend checkout is used, for testing offline.
"""
import os
import secrets
import time

import db

BOOK_PRICE = 99                      # cents
AMOUNTS = (500, 1000, 2000)          # what "Add funds" offers, in cents
KEY = os.environ.get("STRIPE_SECRET_KEY", "")
FAKE = os.environ.get("STRIPE_FAKE") == "1" or not KEY
if KEY and not KEY.startswith(("sk_test_", "rk_test_")):
    raise RuntimeError("STRIPE_SECRET_KEY must be a TEST key (sk_test_...). This app never takes real money.")

if not FAKE:
    import stripe
    stripe.api_key = KEY
    stripe.max_network_retries = 1

_fake_sessions = {}                  # pretend checkout sessions (offline testing only)
APP_TAG = "beanstalk-storybook"      # marks this app's checkouts (the class shares one Stripe test account)


def money(cents):
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


# ---------------------------------------------------------------------------
# Add funds
# ---------------------------------------------------------------------------
def start_checkout(user, amount_cents, base_url):
    if amount_cents not in AMOUNTS:
        raise ValueError("Pick one of the amounts shown.")
    if FAKE:
        sid = "fake_cs_" + secrets.token_hex(8)
        _fake_sessions[sid] = {"user_id": user["id"], "amount": amount_cents, "paid": False}
        return f"{base_url}/billing/fake-checkout?session_id={sid}"
    s = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"quantity": 1, "price_data": {
            "currency": "usd", "unit_amount": amount_cents,
            "product_data": {"name": f"Storybook balance top-up ({money(amount_cents)})"}}}],
        customer_email=user.get("email") if "@" in (user.get("email") or "") else None,
        client_reference_id=str(user["id"]),
        metadata={"user_id": str(user["id"]), "app": APP_TAG},
        success_url=f"{base_url}/wallet?paid={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}/wallet?cancelled=1",
    )
    return s.url


def fake_pay(session_id):
    if session_id in _fake_sessions:
        _fake_sessions[session_id]["paid"] = True


def confirm_checkout(user_id, session_id):
    """Credit a paid checkout exactly once. Returns the amount credited (cents), 0 if not paid."""
    if FAKE:
        s = _fake_sessions.get(session_id)
        if not s or s["user_id"] != user_id or not s["paid"]:
            return 0
        amount = s["amount"]
    else:
        s = stripe.checkout.Session.retrieve(session_id)
        # Stripe objects are not dicts (no .get) in stripe-python 12+: read fields as attributes.
        if getattr(s, "payment_status", None) != "paid" or getattr(s, "client_reference_id", None) != str(user_id):
            return 0
        amount = int(s.amount_total)
    db.post(user_id, "deposit", amount, "Added funds (Stripe test card)", ref=session_id)
    return amount


def reconcile(user_id, base_url):
    """Credit any paid checkout of this user that never got credited (the return trip from Stripe failed, or
    the tab was closed). Each session is credited at most once: its id is the ledger row's unique ref.
    The class shares one Stripe account, so a session only counts if it came back to THIS site's wallet."""
    if FAKE:
        return 0
    added = 0
    since = int(time.time()) - 14 * 24 * 3600
    for s in stripe.checkout.Session.list(limit=100, created={"gte": since}).auto_paging_iter():
        if (getattr(s, "client_reference_id", None) == str(user_id)
                and getattr(s, "payment_status", None) == "paid"
                and str(getattr(s, "success_url", "") or "").startswith(f"{base_url}/wallet")):
            before = db.balance(user_id)
            db.post(user_id, "deposit", int(s.amount_total), "Added funds (Stripe test card)", ref=s.id)
            added += db.balance(user_id) - before
    return added


# ---------------------------------------------------------------------------
# Charging for a book
# ---------------------------------------------------------------------------
def charge_book(user_id, book_id, title):
    """Take $0.99. Returns the ledger row id, or None if the balance is short (nothing is taken)."""
    return db.post(user_id, "book", -BOOK_PRICE, f"Book #{book_id}: {title}", book_id=book_id,
                   ref=f"book-{book_id}", need_funds=True)


# ---------------------------------------------------------------------------
# Refunds: request, then process
# ---------------------------------------------------------------------------
def refundable(user_id, row):
    """How much of this ledger row can still be refunded (cents)."""
    left = abs(row["amount_cents"]) - db.refunded_cents(row["id"])
    if row["kind"] == "book" and row.get("book_id") and db.book_reversed(row["book_id"]):
        return 0                                       # the book failed and its $0.99 was already put back
    if row["kind"] == "deposit":
        left = min(left, db.balance(user_id))          # can't refund money already spent
    return max(0, left) if row["kind"] in ("deposit", "book") else 0


def request_refund(user_id, ledger_id, reason):
    row = db.ledger_row(user_id, ledger_id)
    if not row or row["kind"] not in ("deposit", "book"):
        raise ValueError("Pick a deposit or a book charge to refund.")
    amount = refundable(user_id, row)
    if amount <= 0:
        raise ValueError("Nothing left to refund on that one" +
                         (" (the balance it paid for has been spent)." if row["kind"] == "deposit" else "."))
    kind = "card" if row["kind"] == "deposit" else "book"
    return db.add_refund(user_id, kind, ledger_id, amount, reason or "")


def process_refund(user_id, refund_id):
    r = db.get_refund(user_id, refund_id)
    if not r:
        raise ValueError("Refund not found.")
    if r["status"] != "requested":
        raise ValueError(f"That refund is already {r['status']}.")
    row = db.ledger_row(user_id, r["ledger_id"])
    if r["kind"] == "book":
        db.post(user_id, "book_refund", r["amount_cents"], f"Refund of {row['note']}", book_id=row.get("book_id"),
                ref=f"refund-{refund_id}")
        db.update_refund(refund_id, status="processed", processed_at=db.now(), stripe_ref="to balance")
        return r["amount_cents"]

    # Card refund: take it off the balance first (refused if it's no longer there), then ask Stripe.
    lid = db.post(user_id, "card_refund", -r["amount_cents"], "Refund to card of a deposit", ref=f"refund-{refund_id}",
                  need_funds=True)
    if lid is None:
        db.update_refund(refund_id, status="failed", processed_at=db.now(),
                         error="The balance is lower than the refund now.")
        raise ValueError("Your balance is lower than this refund now, so it can't be sent back to the card.")
    try:
        if FAKE:
            ref = "fake_re_" + secrets.token_hex(6)
        else:
            s = stripe.checkout.Session.retrieve(row["ref"])
            re = stripe.Refund.create(payment_intent=s.payment_intent, amount=r["amount_cents"],
                                      metadata={"user_id": str(user_id), "refund_request": str(refund_id)})
            if re.status not in ("succeeded", "pending"):
                raise RuntimeError(f"Stripe says the refund is {re.status}")
            ref = re.id
    except Exception as e:
        db.post(user_id, "reversal", r["amount_cents"], "Card refund failed, money put back",
                ref=f"refund-undo-{refund_id}")
        db.update_refund(refund_id, status="failed", processed_at=db.now(), error=str(e)[:300])
        raise ValueError(f"Stripe couldn't process the refund: {str(e)[:150]}")
    db.update_refund(refund_id, status="processed", processed_at=db.now(), stripe_ref=ref)
    return r["amount_cents"]
