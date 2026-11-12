"""
The generation engine.

- Every OpenAI call goes through image_call() or analysis_call(), which log the model, time, tokens and the
  dollar cost (from the response's token usage) to the api_calls table.
- A shared limiter keeps image calls under the account's images-per-minute limit (IMAGES_PER_MINUTE).
- run_book() is the per-book job: hero sheet -> every hero page in parallel (paint, analyse, repaint up to 3
  attempts, keep the best) -> PDF. It runs in a background thread and writes its progress to the database,
  so the browser can poll, refresh, or come back later.
- run_pregen() draws the shared character bible and the pre-made scenes (admin only, once).

IMAGE_MODEL=fake makes free placeholder pictures and fake analyses, for testing without spending anything.
"""
import base64
import io
import json
import logging
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps

import db
import stories as S

log = logging.getLogger("beanstalk")

IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-2.5-flare")
FAKE = IMAGE_MODEL == "fake"
QUALITY = os.environ.get("PAGE_QUALITY", "medium")
HERO_QUALITY = os.environ.get("HERO_QUALITY", QUALITY)
SCENE_QUALITY = os.environ.get("SCENE_QUALITY", QUALITY)       # same as the pages, so every page matches
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "gpt-5-mini")
# Tried in order for a bible portrait that IMAGE_MODEL refuses.
BIBLE_FALLBACK_MODELS = [m.strip() for m in os.environ.get("BIBLE_FALLBACK_MODELS", "gpt-image-1.5,gpt-image-1").split(",")
                         if m.strip()]
MAX_ATTEMPTS = 3
RETRY_DEADLINE = float(os.environ.get("RETRY_DEADLINE", "48"))  # seconds after upload: no new repaints after this
IPM = int(os.environ.get("IMAGES_PER_MINUTE", "20"))
WORKERS = int(os.environ.get("PAGE_WORKERS", "16"))
SIZE = "1536x1024"

# $ per 1M tokens (OpenAI pricing for gpt-image-2.5-flare and gpt-5-mini, Nov 2026). Override in the environment.
PRICE = {
    "img_text_in": float(os.environ.get("PRICE_IMG_TEXT_IN", "5")),
    "img_image_in": float(os.environ.get("PRICE_IMG_IMAGE_IN", "8")),
    "img_out": float(os.environ.get("PRICE_IMG_OUT", "30")),
    "llm_in": float(os.environ.get("PRICE_LLM_IN", "0.25")),
    "llm_out": float(os.environ.get("PRICE_LLM_OUT", "2")),
}

_client = None


def client():
    global _client
    if _client is None:
        _client = OpenAI(max_retries=0, timeout=120)   # one call per attempt; our own loop decides repaints
    return _client


# ---------------------------------------------------------------------------
# Images-per-minute limiter (shared by every book being made at once)
# ---------------------------------------------------------------------------
_ipm_lock = threading.Lock()
_ipm_times = deque()


def _wait_for_slot():
    while True:
        with _ipm_lock:
            now = time.time()
            while _ipm_times and now - _ipm_times[0] > 60:
                _ipm_times.popleft()
            if len(_ipm_times) < IPM:
                _ipm_times.append(now)
                return
            wait = 60 - (now - _ipm_times[0]) + 0.05
        time.sleep(min(wait, 2))


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def to_png(raw, max_side=1536):
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def jpeg(img, q=88):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=q)
    return buf.getvalue()


def thumb(raw, w=360):
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((w, w))
    return jpeg(im, 72)


def _fake_image(label, base=None, hero_at=None):
    time.sleep(float(os.environ.get("FAKE_DELAY", "3")) * random.uniform(0.6, 1.4))
    if any(x and label.startswith(x) for x in os.environ.get("FAKE_REFUSE", "").split("|")):   # testing only
        raise RuntimeError("Error code: 400 - Your request was rejected by the safety system (fake)")
    rng = random.Random(label)
    if base:
        im = Image.open(io.BytesIO(base)).convert("RGB").resize((1536, 1024))
    else:
        im = Image.new("RGB", (1536, 1024), tuple(rng.randint(70, 190) for _ in range(3)))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 760, 1536, 1024), fill=(70, 120, 60))                       # plain ground
        d.rectangle((0, 0, 1536, 300), fill=(150, 190, 230))                       # plain sky
        d.ellipse((1100, 380, 1260, 540), fill=(240, 210, 180))                    # a supporting character
    d = ImageDraw.Draw(im)
    if hero_at:
        x = {"left": 300, "center": 768, "right": 1230}[hero_at]
        d.ellipse((x - 70, 380, x + 70, 520), fill=(255, 200, 150), outline=(0, 0, 0), width=4)   # hero face
        d.rectangle((x - 50, 520, x + 50, 740), fill=(180, 60, 50))
    d.text((40, 960), f"TEST IMAGE - {label}", fill=(255, 255, 255))
    return jpeg(im, 85)


def image_call(images, prompt, *, purpose, label, user_id=None, book_id=None, quality=None, hero_at=None,
               model=None):
    """Exactly one image API call. images: list of PNG bytes (edit) or [] (generate). Returns JPEG bytes."""
    quality = quality or QUALITY
    model = model or IMAGE_MODEL
    _wait_for_slot()
    t0 = time.time()
    usage = None
    try:
        if FAKE:
            out = _fake_image(label, base=images[0] if images and purpose in ("page", "retry") else None,
                              hero_at=hero_at)
            usage = {"text": 600, "image_in": 1500 * len(images), "out": 1600 if quality == "medium" else 3500}
        else:
            files = [(f"in{i}.png", b, "image/png") for i, b in enumerate(images)]
            kw = dict(model=model, prompt=prompt, size=SIZE, quality=quality, n=1, output_format="jpeg",
                      output_compression=88)
            if files:
                r = client().images.edit(image=files if len(files) > 1 else files[0], **kw)
            else:
                # Drawing from scratch (the character bible) accepts a looser moderation level; the strict
                # default refused a plain picture-book farm woman every time. Edits have no such setting.
                r = client().images.generate(moderation=os.environ.get("IMAGE_MODERATION", "low"), **kw)
            out = base64.b64decode(r.data[0].b64_json)
            u = getattr(r, "usage", None)
            if u:
                det = getattr(u, "input_tokens_details", None)
                text_in = getattr(det, "text_tokens", None) if det else None
                img_in = getattr(det, "image_tokens", None) if det else None
                if text_in is None:
                    text_in, img_in = getattr(u, "input_tokens", 0), 0
                usage = {"text": text_in or 0, "image_in": img_in or 0, "out": getattr(u, "output_tokens", 0) or 0}
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        log.warning("image FAIL %s book=%s %s ms=%d err=%s", purpose, book_id, label, ms, str(e)[:200])
        db.log_call(user_id=user_id, book_id=book_id, purpose=purpose, model=model, ms=ms, ok=0,
                    input_tokens=0, output_tokens=0, cost_usd=0.0, detail=f"{label}: {str(e)[:250]}")
        raise
    ms = int((time.time() - t0) * 1000)
    if usage:
        cost = (usage["text"] * PRICE["img_text_in"] + usage["image_in"] * PRICE["img_image_in"]
                + usage["out"] * PRICE["img_out"]) / 1e6
        tin, tout = usage["text"] + usage["image_in"], usage["out"]
    else:                                   # no usage reported: fall back to a per-image estimate
        cost, tin, tout = float(os.environ.get("IMAGE_COST_FALLBACK", "0.06")), 0, 0
    log.info("image OK %s book=%s %s ms=%d cost=$%.4f", purpose, book_id, label, ms, cost)
    db.log_call(user_id=user_id, book_id=book_id, purpose=purpose, model=model, ms=ms, ok=1,
                input_tokens=tin, output_tokens=tout, cost_usd=cost, detail=label)
    return out


def _data_url(raw, max_side=768):
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((max_side, max_side))
    return "data:image/jpeg;base64," + base64.b64encode(jpeg(im, 80)).decode()


def analysis_call(images, prompt, *, label, user_id=None, book_id=None, fake_hint=None, detail="low",
                  effort="minimal"):
    """One vision call that grades a picture. Returns the parsed JSON dict."""
    t0 = time.time()
    try:
        if FAKE:
            time.sleep(float(os.environ.get("FAKE_DELAY", "3")) * 0.3)
            rng = random.Random(label + str(time.time()))
            bad = rng.random() < 0.3                     # fail sometimes, so the repaint loop is exercised
            busy = {"top": [False] * 3, "middle": [True, False, True], "bottom": [False] * 3}
            expr = rng.randint(7, 10)
            if fake_hint:                                # mark the hero's column busy in the middle row
                busy["middle"][{"left": 0, "center": 1, "right": 2}[fake_hint]] = True
            a = {"hero": 4 if bad else rng.randint(7, 10), "story": rng.randint(7, 10), "anatomy": rng.randint(7, 10),
                 "clean": 10, "expression": expr, "issues": ["hero face doesn't match the sheet"] if bad else [],
                 "busy": busy}
            tin, tout = 2200, 180
        else:
            content = [{"type": "text", "text": prompt}] + [
                {"type": "image_url", "image_url": {"url": _data_url(b, 1536 if detail == "high" else 768),
                                                     "detail": detail}} for b in images]
            kw = {}
            if ANALYSIS_MODEL.startswith("gpt-5"):
                kw["reasoning_effort"] = effort
            r = client().chat.completions.create(model=ANALYSIS_MODEL, response_format={"type": "json_object"},
                                                 messages=[{"role": "user", "content": content}], **kw)
            a = json.loads(r.choices[0].message.content)
            tin, tout = r.usage.prompt_tokens, r.usage.completion_tokens
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        db.log_call(user_id=user_id, book_id=book_id, purpose="analysis", model=ANALYSIS_MODEL, ms=ms, ok=0,
                    input_tokens=0, output_tokens=0, cost_usd=0.0, detail=f"{label}: {str(e)[:250]}")
        raise
    ms = int((time.time() - t0) * 1000)
    cost = (tin * PRICE["llm_in"] + tout * PRICE["llm_out"]) / 1e6
    db.log_call(user_id=user_id, book_id=book_id, purpose="analysis", model=ANALYSIS_MODEL, ms=ms, ok=1,
                input_tokens=tin, output_tokens=tout, cost_usd=cost, detail=label)
    return a


UNCHECKED = {"unchecked": True, "issues": ["the automatic check was unavailable, so this picture wasn't graded"]}


def safe_analysis(*args, **kw):
    """A failed check must not trigger repaints: the picture is kept, marked unchecked, words go below it."""
    try:
        return analysis_call(*args, **kw)
    except Exception as e:
        log.warning("analysis unavailable: %s", str(e)[:300])
        if pregen_state["running"]:
            _plog(f"check failed: {str(e)[:300]}")
        return {"unchecked": True, "issues": [UNCHECKED["issues"][0]], "error": str(e)[:300]}


def grade(a):
    """Overall score out of 10 and pass/fail. The hero's likeness counts double."""
    if a.get("unchecked"):
        return None, True
    def g(k):
        try:
            return max(0.0, min(10.0, float(a.get(k, 0))))
        except (TypeError, ValueError):
            return 0.0
    parts = {k: g(k) for k in ("hero", "story", "anatomy", "clean")}
    parts["expression"] = g("expression") if "expression" in a else 10.0
    score = (2 * parts["hero"] + parts["story"] + parts["anatomy"] + parts["clean"] + parts["expression"]) / 6
    return round(score, 1), min(parts.values()) >= 6 and score >= 7


def clear_zone(page, busy):
    """Where the words go. A 'full' page uses the first allowed band with nothing important in it; if none is
    clear (or the page is 'framed'), the words go on the paper below the picture, where they can't cover it."""
    if page["layout"] != "full":
        return "below"
    busy = busy or {}
    for z in page["zones"]:
        row = busy.get(z)
        if isinstance(row, list) and len(row) == 3 and not any(row):
            return z
    return "below"


# ---------------------------------------------------------------------------
# One book
# ---------------------------------------------------------------------------
_running = set()
_running_lock = threading.Lock()


def start_book(book_id, user_id, photo_png):
    with _running_lock:
        _running.add(book_id)
    threading.Thread(target=_run_book_safe, args=(book_id, user_id, photo_png), daemon=True).start()


def is_running(book_id):
    return book_id in _running


def _run_book_safe(book_id, user_id, photo_png):
    try:
        run_book(book_id, user_id, photo_png)
    except Exception as e:
        log.exception("book %s failed", book_id)
        msg = str(e)
        if "safety system" in msg:
            fail_book(book_id, user_id, "OpenAI's safety filter declined this photo. Try a different photo: one person, "
                                        "facing the camera, in everyday clothes.")
        else:
            fail_book(book_id, user_id, f"Something went wrong while making the book ({msg[:160]}).")
    finally:
        with _running_lock:
            _running.discard(book_id)


def fail_book(book_id, user_id, message):
    """Mark the book failed and give the $0.99 back (once)."""
    b = db.get_book_internal(book_id)
    db.update_book(book_id, status="failed", stage="Failed", error=message[:400])
    if b and b.get("charge_id"):
        db.post(user_id, "reversal", 99, f"Refund: book #{book_id} could not be made", book_id=book_id,
                ref=f"reversal-{book_id}")


def run_book(book_id, user_id, photo_png):
    b = db.get_book_internal(book_id)
    story, t0 = b["story"], b["started_at"]
    pages = S.STORIES[story]["pages"]
    name = b["child_name"] or "your child"

    # Shared art must exist before a book can be made.
    missing = [p["n"] for p in pages if db.get_scene(story, p["n"], thumb=True)[0] is None]
    if missing:
        raise RuntimeError(f"the pre-made scenes for this story aren't ready (missing pages {missing[:5]})")

    db.init_pages(book_id, [p["n"] for p in pages])

    # Pages without the hero are the pre-made scenes as they are; they're ready at once.
    for p in pages:
        if not p["hero"]:
            img, a = db.get_scene(story, p["n"])
            db.set_page(book_id, p["n"], status="done", attempts=0, score=None, zone=clear_zone(p, a.get("busy")),
                        image=img, thumb=thumb(img), issues="pre-made scene, checked once when it was made")

    # 1. The hero sheet: this book's entry in the character bible. Analysed, up to 3 attempts.
    db.update_book(book_id, stage=f"Drawing {name} as {S.HERO[story]['role']}")
    hero, best = None, None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        img = image_call([photo_png], S.hero_prompt(story), purpose="hero" if attempt == 1 else "retry",
                         label=f"hero try {attempt}", user_id=user_id, book_id=book_id, quality=HERO_QUALITY)
        a = safe_analysis([img, photo_png], hero_check_prompt(story), label=f"hero check {attempt}",
                          user_id=user_id, book_id=book_id)
        score, ok = grade(a)
        db.add_attempt(book_id, 0, attempt, score, ok, a, img)
        if best is None or (score or 0) > (best[0] or 0):
            best = (score, img)
        if ok or time.time() - t0 > RETRY_DEADLINE / 2:
            break
        db.update_book(book_id, stage=f"Redrawing {name} (attempt {attempt + 1} of 3)")
    hero = best[1]
    db.update_book(book_id, hero=hero)
    hero_png = to_png(hero)

    # 2. Every hero page at once.
    db.update_book(book_id, stage="Painting the pages")

    def make_page(p):
        n = p["n"]
        scene, _ = db.get_scene(story, n)
        scene_png = to_png(scene)
        best, tries, last_err = None, 0, ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            tries = attempt
            db.set_page(book_id, n, status="painting", attempts=attempt)
            try:
                img = image_call([scene_png, hero_png], S.insert_prompt(story, p),
                                 purpose="page" if attempt == 1 else "retry", label=f"page {n} try {attempt}",
                                 user_id=user_id, book_id=book_id, hero_at=p["hero"])
            except Exception as e:          # e.g. a safety rejection: count it as a failed try
                last_err = str(e)
                if time.time() - t0 > RETRY_DEADLINE:
                    break
                continue
            db.set_page(book_id, n, status="checking", thumb=thumb(img))
            a = safe_analysis([img, hero], S.analysis_prompt(story, p, True), label=f"page {n} check {attempt}",
                              user_id=user_id, book_id=book_id, fake_hint=p["hero"])
            score, ok = grade(a)
            db.add_attempt(book_id, n, attempt, score, ok, a, img)
            if best is None or (score or 0) > (best[0] or 0):
                best = (score, ok, img, a, attempt)
            if ok:
                break
            if time.time() - t0 > RETRY_DEADLINE:
                break
        if best is None:                    # every try was refused: keep the pre-made scene so the book still exists
            _, sa = db.get_scene(story, n)
            why = "OpenAI's safety filter declined it" if "safety" in last_err else last_err[:120]
            db.set_page(book_id, n, status="done", score=None, image=scene, thumb=thumb(scene),
                        zone=clear_zone(p, (sa or {}).get("busy")),
                        issues=f"no try passed; the hero couldn't be added to this page ({why}), so the scene is shown without them")
            return
        score, ok, img, a, att = best
        note = "; ".join(a.get("issues") or [])[:300]
        if not ok:
            note = f"no try passed; kept the best of {tries} (try {att}): " + note
        db.set_page(book_id, n, status="done", score=score, image=img, thumb=thumb(img),
                    zone=clear_zone(p, a.get("busy")), issues=note)

    hero_pages = [p for p in pages if p["hero"]]
    with ThreadPoolExecutor(min(WORKERS, len(hero_pages))) as ex:
        futures = [ex.submit(make_page, p) for p in hero_pages]
        errors = []
        for f in futures:
            try:
                f.result()
            except Exception as e:
                errors.append(str(e))
    if errors:
        raise RuntimeError(f"{len(errors)} page(s) could not be painted: {errors[0][:120]}")

    # 3. The PDF, built once and stored, so it downloads instantly from now on.
    db.update_book(book_id, stage="Putting the book together")
    from book_pdf import build_book
    b = db.get_book_internal(book_id)
    imgs = db.page_images_internal(book_id)
    pdf = build_book(story, imgs, hero, b)
    db.update_book(book_id, pdf=pdf, status="done", stage="Done", done_at=time.time())
    log.info("book %s done in %.1fs", book_id, time.time() - t0)


def hero_check_prompt(story):
    return ("You are the quality checker for a children's picture book. Image 1 is a character sheet made from the "
            "photo in image 2: a face close-up on the left and the same character full-length on the right, in "
            f"the costume of {S.HERO[story]['role']}. Score from 0 to 10, strictly:\n"
            "- hero: the character is clearly the same person as the photo (face shape, eyes, nose, hair, skin, "
            "glasses, age)\n- story: the sheet shows a close-up and a full-length view in the costume\n"
            "- anatomy: hands have five fingers, no extra limbs, face not distorted\n"
            "- clean: no letters, words, labels, watermarks or extra people\n"
            "Reply with only JSON: {\"hero\":int,\"story\":int,\"anatomy\":int,\"clean\":int,\"issues\":[strings]}")


# ---------------------------------------------------------------------------
# Shared art: the character bible and the pre-made scenes (admin only)
# ---------------------------------------------------------------------------
pregen_state = {"running": False, "log": deque(maxlen=200), "done": 0, "total": 0}


def _plog(msg):
    pregen_state["log"].appendleft(time.strftime("%H:%M:%S ") + msg)
    log.info("pregen %s", msg)


def start_pregen(story, only=None, redo=False):
    if pregen_state["running"]:
        return False
    pregen_state["running"] = True
    threading.Thread(target=_pregen_safe, args=(story, only, redo), daemon=True).start()
    return True


def _pregen_safe(story, only, redo):
    try:
        run_pregen(story, only, redo)
    except Exception as e:
        _plog(f"stopped: {e}")
    finally:
        pregen_state["running"] = False


def run_pregen(story, only=None, redo=False):
    """only: None (everything missing), 'bible', 'bible:<key>' (one character), or a list of scene numbers."""
    have_scenes, have_bible = db.scene_status()
    for k in S.BIBLE[story]:                       # described-in-words characters keep no portrait
        if S.text_only(story, k):
            db.delete_bible(story, k)
    chars = [k for k in S.BIBLE[story] if not S.text_only(story, k) and (redo or f"{story}:{k}" not in have_bible)]
    if isinstance(only, str) and only.startswith("bible:"):
        chars = [only[6:]] if only[6:] in S.BIBLE[story] and not S.text_only(story, only[6:]) else []
    elif only not in (None, "bible"):
        chars = []
    pages = S.STORIES[story]["pages"]
    if isinstance(only, str) and only.startswith("bible"):
        todo = []
    elif isinstance(only, list):
        todo = [p for p in pages if p["n"] in only]
    else:
        todo = [p for p in pages if redo or f"{story}:{p['n']}" not in have_scenes]
    pregen_state.update(done=0, total=len(chars) + len(todo))

    def char(k):
        name, desc = S.BIBLE[story][k]
        img = None
        # Each image model has its own safety check; if one refuses a plain picture-book character, try the
        # next one, each with the full prompt and then a plainer wording. Scenes are still painted by
        # IMAGE_MODEL, so the style of every page stays the same.
        for m in [IMAGE_MODEL] + [x for x in BIBLE_FALLBACK_MODELS if x != IMAGE_MODEL]:
            for variant, prompt in (("full", S.bible_prompt(story, k)), ("plain", S.bible_prompt_plain(story, k))):
                try:
                    img = image_call([], prompt, purpose="bible", label=f"{story} bible {k} [{m} {variant}]",
                                     quality=SCENE_QUALITY, model=m)
                    if m != IMAGE_MODEL or variant != "full":
                        _plog(f"{story}: {name} drawn with {m} ({variant} wording)")
                    break
                except Exception as e:
                    _plog(f"{story}: {name} refused by {m} ({variant} wording): {str(e)[:140]}")
            if img:
                break
        if img is None:
            # Fallback: lift the character out of a scene they already appear in (an edit, not a fresh drawing).
            have, _ = db.scene_status()
            src = next((q["n"] for q in S.STORIES[story]["pages"] if k in q["cast"] and f"{story}:{q['n']}" in have), None)
            if src is None:
                _plog(f"{story}: {name} will be drawn from the description in each scene for now")
                return
            try:
                scene_img, _ = db.get_scene(story, src)
                img = image_call([to_png(scene_img, 1024)], S.bible_from_scene_prompt(story, k), purpose="bible",
                                 label=f"{story} bible {k} from scene {src}", quality=SCENE_QUALITY)
                _plog(f"{story}: drew {name} from scene {src} instead")
            except Exception as e2:
                _plog(f"{story}: {name} refused again from scene {src}: {str(e2)[:160]}. "
                      "Scenes will draw them from the description until this is fixed.")
                return
        db.save_bible(story, k, name, desc, img)
        pregen_state["done"] += 1
        _plog(f"{story}: drew {name}")

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(char, chars))

    def scene(p):
        try:
            _scene(p)
        except Exception as e:                  # one failure must not stop the rest
            _plog(f"{story}: scene {p['n']} FAILED: {str(e)[:400]}")

    def _scene(p):
        missing = [c for c in p["cast"] if not S.text_only(story, c) and not db.bible_image(story, c)]
        if missing:
            _plog(f"{story}: scene {p['n']}: drawing {', '.join(missing)} from the description (no bible picture yet)")
        refs = [to_png(db.bible_image(story, c), 1024) for c in p["cast"]
                if not S.text_only(story, c) and db.bible_image(story, c)]
        best, last_err = None, ""
        prompt = S.scene_prompt(story, p)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                img = image_call(refs, prompt, purpose="scene",
                                 label=f"{story} scene {p['n']} try {attempt}", quality=SCENE_QUALITY)
            except Exception as e:              # a refused try is a failed attempt; earlier good tries are kept
                last_err = str(e)
                if refs and "safety" in last_err:
                    # A reference picture can trip the filter on its own; try the next attempt from words only.
                    refs = []
                    prompt = prompt.replace(S.REFS_SENTENCE, "")
                    _plog(f"{story}: scene {p['n']} refused with reference pictures; next try uses words only")
                continue
            a = safe_analysis([img] + [b for b in (db.bible_image(story, c) for c in p["cast"] if not S.text_only(story, c))
                                       if b][:3],
                              scene_check_prompt(story, p), label=f"{story} scene {p['n']} check {attempt}",
                              detail="high", effort="low")   # one-time art: worth a closer look
            score, ok = grade(a)
            if a.get("extra_figure") is True:
                ok = False
                a.setdefault("issues", []).append("a child or an unlisted character is in the scene")
            if a.get("off_model") is True:
                ok = False
                a.setdefault("issues", []).append("a character doesn't match their reference sheet")
            # The words' band must be clear in the scene itself, or the template can't be honoured.
            # (An unchecked scene is kept as is: a failed check must never cause a repaint.)
            if not a.get("unchecked") and p["layout"] == "full" and clear_zone(p, a.get("busy")) != p["zones"][0]:
                ok = False
                a.setdefault("issues", []).append(f"the {p['zones'][0]} band isn't clear for the words")
            if best is None or (ok, score or 0) > (best[0], best[1] or 0):
                best = (ok, score, img, a, attempt)
            if ok:
                break
        if best is None:
            raise RuntimeError(f"all 3 tries refused: {last_err[:300]}")
        ok, score, img, a, att = best
        db.save_scene(story, p["n"], img, thumb(img), att, score, a)
        pregen_state["done"] += 1
        _plog(f"{story}: scene {p['n']} {'ok' if ok else 'kept best'} (score {score}, tries {att})")

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(scene, todo))
    have_scenes, have_bible = db.scene_status()
    miss_b = [S.BIBLE[story][k][0] for k in S.BIBLE[story]
              if f"{story}:{k}" not in have_bible and not S.text_only(story, k)]
    miss_s = [p["n"] for p in pages if f"{story}:{p['n']}" not in have_scenes]
    if miss_b or miss_s:
        _plog(f"{story}: stopped with gaps. Missing characters: {', '.join(miss_b) or 'none'}; "
              f"missing scenes: {', '.join(map(str, miss_s)) or 'none'}. See the errors above.")
    else:
        _plog(f"{story}: complete. All characters and all 20 scenes are drawn.")


def scene_check_prompt(story, p):
    return S.analysis_prompt(story, p, False).replace(
        "Image 1 is one generated page.",
        "Image 1 is one generated page; any further images are the reference sheets of its characters."
        + (" The hero is added later, so an empty spot in the scene is correct." if p["hero"] else "")
        + f" IMPORTANT: this scene must contain no child, boy, girl or {S.HERO[story]['role']} at all (the child "
          "is added later, separately), and no people other than the listed characters. Look closely, including "
          "small figures in the distance. Also check that each listed character looks like their reference sheet "
          "(the same design, colours and clothes) and is doing what the page describes."
          ).replace('"issues":[short strings]',
                    '"extra_figure":bool (true if any child or anyone not listed appears),'
                    '"off_model":bool (true if a listed character looks different from their reference sheet '
                    'or the description),"issues":[short strings]')
