"""
Lulu Print API client (sandbox by default: orders are accepted and tracked but never printed, shipped or charged).

Docs: https://api.lulu.com/docs/  ·  sandbox accounts: https://developers.sandbox.lulu.com
Env: LULU_CLIENT_KEY, LULU_CLIENT_SECRET (from the sandbox account's API Keys page), LULU_API_BASE (defaults to the
sandbox; never point it at production in this class), LULU_POD_PACKAGE (the product: trim, color, paper, binding).
LULU_FAKE=1 answers locally with made-up numbers, for testing without an account.
"""
import os
import random
import threading
import time

import requests

BASE = os.environ.get("LULU_API_BASE", "https://api.sandbox.lulu.com").rstrip("/")
KEY = os.environ.get("LULU_CLIENT_KEY", "")
SECRET = os.environ.get("LULU_CLIENT_SECRET", "")
FAKE = os.environ.get("LULU_FAKE") == "1"
# 11 x 8.5 in landscape, full color, standard quality, hardcover (casewrap), 80# coated white paper, gloss cover.
# Checked against the sandbox: Lulu has no stapled book at this size, a paperback needs 32+ pages, and a hardcover
# takes 24 or more, which is what a picture book is anyway.
POD_PACKAGE = os.environ.get("LULU_POD_PACKAGE", "1100X0850FCSTDCW080CW444GXX")
# What Lulu offers for this hardcover to US addresses (GROUND is refused for this product: checked in the sandbox).
SHIPPING_LEVELS = {"MAIL": "Standard mail", "EXPEDITED": "Expedited", "EXPRESS": "Express"}

_tok = {"value": None, "exp": 0}
_lock = threading.Lock()


class LuluError(RuntimeError):
    pass


def configured():
    return FAKE or bool(KEY and SECRET)


def _token():
    with _lock:
        if _tok["value"] and time.time() < _tok["exp"] - 60:
            return _tok["value"]
        r = requests.post(f"{BASE}/auth/realms/glasstree/protocol/openid-connect/token",
                          data={"grant_type": "client_credentials"}, auth=(KEY, SECRET), timeout=30)
        if r.status_code != 200:
            raise LuluError(f"Lulu sign-in failed ({r.status_code}): {r.text[:200]}")
        d = r.json()
        _tok["value"], _tok["exp"] = d["access_token"], time.time() + int(d.get("expires_in", 3600))
        return _tok["value"]


def _call(method, path, json=None):
    r = requests.request(method, f"{BASE}{path}", json=json, timeout=60,
                         headers={"Authorization": f"Bearer {_token()}", "Cache-Control": "no-cache"})
    if r.status_code >= 400:
        raise LuluError(f"Lulu {method} {path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def cost(page_count, address, shipping_level):
    """Lulu's price for one copy shipped to address: {'print', 'shipping', 'fulfillment', 'tax', 'total'} in USD."""
    if FAKE:
        ship = {"MAIL": 5.69, "EXPEDITED": 20.74, "EXPRESS": 35.74}[shipping_level]
        sub = 12.50 + ship + 0.75
        return {"print": 12.50, "shipping": ship, "fulfillment": 0.75, "tax": round(sub * 0.08, 2),
                "total": round(sub * 1.08, 2), "currency": "USD", "raw": {}}
    d = _call("POST", "/print-job-cost-calculations/", {
        "line_items": [{"page_count": page_count, "pod_package_id": POD_PACKAGE, "quantity": 1}],
        "shipping_address": _addr(address), "shipping_option": shipping_level})
    item = (d.get("line_item_costs") or [{}])[0]
    num = lambda x: float(x or 0)
    return {"print": num(item.get("total_cost_excl_tax")),
            "shipping": num((d.get("shipping_cost") or {}).get("total_cost_excl_tax")),
            "fulfillment": num((d.get("fulfillment_cost") or {}).get("total_cost_excl_tax")),
            "tax": num(d.get("total_tax")), "total": num(d.get("total_cost_incl_tax")),
            "currency": d.get("currency", "USD"), "raw": d}


def cover_size(page_count):
    """The cover spread's width and height in points, from Lulu (spine width depends on product and pages)."""
    if FAKE:
        return None
    d = _call("POST", "/cover-dimensions/", {"pod_package_id": POD_PACKAGE, "interior_page_count": page_count,
                                              "unit": "pt"})
    return float(d["width"]), float(d["height"])


def create_job(order_id, title, interior_url, cover_url, address, shipping_level, email):
    if FAKE:
        return {"id": random.randint(100000, 999999), "status": {"name": "CREATED"}}
    return _call("POST", "/print-jobs/", {
        "contact_email": email,
        "external_id": f"order-{order_id}",
        "line_items": [{"external_id": f"order-{order_id}-book", "title": title[:255], "quantity": 1,
                        "pod_package_id": POD_PACKAGE,
                        "printable_normalization": {"interior": {"source_url": interior_url},
                                                    "cover": {"source_url": cover_url}}}],
        "shipping_address": _addr(address),
        "shipping_level": shipping_level,
    })


def job_status(lulu_id):
    """Lulu's current status for a print job, e.g. CREATED, UNPAID, PRODUCTION_DELAYED, IN_PRODUCTION, SHIPPED,
    REJECTED (with a message), CANCELED."""
    if FAKE:
        return {"name": "CREATED", "messages": {}}
    d = _call("GET", f"/print-jobs/{lulu_id}/")
    return d.get("status") or {}


def _addr(a):
    out = {"name": a.get("name", ""), "street1": a.get("street1", ""), "city": a.get("city", ""),
           "state_code": a.get("state_code", ""), "postcode": a.get("postcode", ""),
           "country_code": a.get("country_code", "US"), "phone_number": a.get("phone_number", "")}
    if a.get("street2"):
        out["street2"] = a["street2"]
    return out
