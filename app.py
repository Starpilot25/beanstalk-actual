"""
Cartoon Yourself into Jack and the Beanstalk — MCON 368 homework.

Flow (each step is exactly ONE API call, triggered by one button click — no loops):
  1. POST /api/cartoonify  photo + style settings      -> cartoon portrait
  2. POST /api/scene       photo + cartoon + scene id  -> cartoon person in the scene,
                                                          captioned with the scene spec sent

The API key is read from the OPENAI_API_KEY environment variable only.
"""

import base64
import io
import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from PIL import Image, ImageOps

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB per request

MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1-mini")

# max_retries=0: the SDK retries failed calls by default, which would be a hidden
# loop around the API call. Exactly one attempt per click.
_client = None


def client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not set on the server.")
        _client = OpenAI(api_key=key, max_retries=0, timeout=170)
    return _client


# ---------------------------------------------------------------------------
# Scene specifications. The exact string sent to the model is the caption.
# ---------------------------------------------------------------------------
SCENES = {
    "planting": (
        "Jack kneels in a freshly dug garden row beside his small thatched cottage "
        "on a sunny morning, pressing three magic beans into the dark soil with his "
        "fingertips. A small cloth pouch lies open next to his knee and a watering can "
        "stands nearby. No beanstalk has grown yet - only bare soil."
    ),
    "climbing": (
        "Jack climbs hand over hand up an enormous twisting green beanstalk, both hands "
        "gripping a thick vine and one foot braced on a broad leaf. He looks up toward "
        "the clouds just above him; his tiny thatched cottage and fields are far below."
    ),
}

# ---------------------------------------------------------------------------
# User-adjustable cartoon settings -> prompt fragments (whitelisted values only).
# ---------------------------------------------------------------------------
STYLES = {
    "storybook3d": "a polished 3D animated-film character with soft rounded forms and gentle lighting",
    "flat": "a clean flat-vector cartoon with simple shapes and crisp, even outlines",
    "watercolor": "a hand-painted watercolor picture-book illustration with soft ink lines",
    "comic": "a bold comic-book illustration with strong black ink lines and cel shading",
}
EXAGGERATION = {
    "subtle": "Keep proportions close to real life; only lightly stylize.",
    "moderate": "Slightly larger head and eyes, moderately simplified features.",
    "strong": "Playful caricature: big head, big expressive eyes, but the same recognizable features.",
}
PALETTES = {
    "vivid": "bright, saturated colors",
    "pastel": "soft pastel colors",
    "earthy": "warm, earthy, muted fairy-tale colors",
}
QUALITIES = {"low", "medium"}  # "high" deliberately left out to protect the budget

IDENTITY_RULES = (
    "IDENTITY IS THE TOP PRIORITY. The character must be clearly recognizable as the "
    "person in the reference photo: keep the same face shape, eye shape and spacing, "
    "nose, mouth, eyebrows, skin tone, hairline, hair color, hair length and hairstyle, "
    "facial hair, glasses, and any distinctive marks exactly as in the photo. Do not "
    "change apparent age, gender, or ethnicity. Do not beautify or swap in a generic face."
)


def read_settings(form):
    style = form.get("style", "storybook3d")
    exag = form.get("exaggeration", "moderate")
    palette = form.get("palette", "vivid")
    quality = form.get("quality", "low")
    if style not in STYLES or exag not in EXAGGERATION or palette not in PALETTES or quality not in QUALITIES:
        raise ValueError("Invalid setting.")
    return style, exag, palette, quality


def style_sentence(style, exag, palette):
    return f"Art style: {STYLES[style]}, {PALETTES[palette]}. {EXAGGERATION[exag]}"


def cartoon_prompt(style, exag, palette):
    return (
        "Turn the person in this photo into a cartoon character portrait. "
        f"{style_sentence(style, exag, palette)} "
        f"{IDENTITY_RULES} "
        "Head-and-shoulders, facing the viewer, plain light background, no text."
    )


def scene_prompt(scene_spec, style, exag, palette):
    return (
        "Image 1 is a cartoon character; image 2 is the real photo of the same person. "
        "Draw this exact character as Jack in a Jack and the Beanstalk storybook "
        "illustration, dressed in simple peasant clothes (linen shirt, brown vest, trousers). "
        f"{style_sentence(style, exag, palette)} Match the character's look in image 1 and "
        f"the face in image 2. {IDENTITY_RULES} "
        "The face must be clearly visible, unobstructed, and turned at least partly toward "
        "the viewer. "
        f"SCENE (depict every element exactly): {scene_spec} "
        "Full scene, wide enough to show all scene elements. No text, captions, or speech bubbles."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_image(raw: bytes, name: str) -> tuple:
    """Fix phone rotation, convert to RGB PNG, cap at 1024px to keep input cost low."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise ValueError("That file isn't a readable image (use JPG, PNG, or WEBP).")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def uploaded_photo():
    f = request.files.get("photo")
    if not f or not f.filename:
        raise ValueError("Please upload a photo.")
    return normalize_image(f.read(), "photo.png")


# Very small per-IP limiter so a public URL can't drain the balance.
_hits = defaultdict(deque)
LIMIT, WINDOW = int(os.environ.get("HOURLY_LIMIT", "30")), 3600


def rate_limited():
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= LIMIT:
        return True
    q.append(now)
    return False


def call_edit(images, prompt, quality, size):
    """Exactly one image-edit call. No retries, no loops."""
    result = client().images.edit(
        model=MODEL,
        image=images,
        prompt=prompt,
        input_fidelity="high",  # preserves facial features from the reference images
        quality=quality,
        size=size,
        n=1,
    )
    return result.data[0].b64_json


def error(msg, code=400):
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html", scenes=SCENES)


@app.get("/healthz")
def health():
    return "ok"


@app.post("/api/cartoonify")
def cartoonify():
    if rate_limited():
        return error("Hourly limit reached — try again later.", 429)
    try:
        photo = uploaded_photo()
        style, exag, palette, quality = read_settings(request.form)
        b64 = call_edit(photo, cartoon_prompt(style, exag, palette), quality, "1024x1024")
        return jsonify({"image": b64})
    except ValueError as e:
        return error(str(e))
    except Exception as e:  # surface API errors (bad key, safety block, quota) plainly
        app.logger.exception("cartoonify failed")
        return error(f"Generation failed: {getattr(e, 'message', str(e))}", 502)


@app.post("/api/scene")
def scene():
    if rate_limited():
        return error("Hourly limit reached — try again later.", 429)
    try:
        scene_id = request.form.get("scene")
        if scene_id not in SCENES:
            raise ValueError("Unknown scene.")
        spec = SCENES[scene_id]
        photo = uploaded_photo()
        cartoon_b64 = request.form.get("cartoon", "")
        if not cartoon_b64:
            raise ValueError("Cartoonify the photo first.")
        try:
            cartoon_raw = base64.b64decode(cartoon_b64, validate=True)
        except Exception:
            raise ValueError("Cartoon image was corrupted; cartoonify again.")
        cartoon = normalize_image(cartoon_raw, "cartoon.png")
        style, exag, palette, quality = read_settings(request.form)
        size = "1024x1536" if scene_id == "climbing" else "1536x1024"
        b64 = call_edit([cartoon, photo], scene_prompt(spec, style, exag, palette), quality, size)
        # The caption is the scene specification exactly as sent to the model.
        return jsonify({"image": b64, "caption": spec})
    except ValueError as e:
        return error(str(e))
    except Exception as e:
        app.logger.exception("scene failed")
        return error(f"Generation failed: {getattr(e, 'message', str(e))}", 502)


@app.errorhandler(413)
def too_big(_):
    return error("Image too large — keep uploads under about 10 MB.", 413)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
