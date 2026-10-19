"""
Cartoon Yourself into Jack and the Beanstalk — MCON 368 homework.

Flow (each button click = exactly ONE API call; there are no loops or retries around any call):
  1. POST /api/cartoonify  photo + cartoon settings          -> cartoon portrait
  2. POST /api/scene       photo + cartoon + scene options    -> cartoon person in the scene,
                                                                captioned with the exact scene spec sent
  3. POST /api/check       generated scene + its scene spec   -> AI checklist: is every element
                                                                of the caption visible? (optional QA)

The API key is read from the OPENAI_API_KEY environment variable only.
"""

import base64
import io
import json
import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from PIL import Image, ImageOps

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # generated scenes are sent back for the check step
# Flask 3.1+ caps non-file form fields at 500 KB by default; the cartoon and the generated
# scene are sent back as base64 text fields (2-5 MB), so raise that cap too.
app.config["MAX_FORM_MEMORY_SIZE"] = 32 * 1024 * 1024

IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1-mini")
CHECK_MODEL = os.environ.get("CHECK_MODEL", "gpt-4.1-mini")

# max_retries=0: the SDK silently retries failed calls by default, which would be a hidden
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
# Cartoon settings (whitelisted values -> prompt fragments)
# ---------------------------------------------------------------------------
STYLES = {
    "storybook3d": "a polished 3D animated-feature-film character with soft rounded forms and warm cinematic lighting",
    "flat": "a clean flat-vector cartoon with simple geometric shapes and crisp, even outlines",
    "watercolor": "a hand-painted watercolor picture-book illustration with delicate ink linework",
    "comic": "a bold comic-book illustration with strong black ink lines and cel shading",
    "anime": "a cel-shaded Japanese anime illustration with clean lines and expressive eyes",
    "clay": "a stop-motion claymation figure with visible sculpted clay texture and soft studio lighting",
    "papercut": "a layered paper-cutout collage illustration with textured paper and soft drop shadows",
    "vintage": "a 1950s golden-age children's book illustration with gouache texture and limited print colors",
}
EXAGGERATION = {
    "subtle": "Keep proportions close to real life; stylize only lightly.",
    "moderate": "Slightly larger head and eyes, moderately simplified features.",
    "strong": "Playful caricature: big head and big expressive eyes, while keeping every recognizable feature.",
}
PALETTES = {
    "vivid": "bright, saturated colors",
    "pastel": "soft pastel colors",
    "earthy": "warm, earthy, muted fairy-tale colors",
    "moonlit": "cool blues and silvers with warm lamplight accents",
}
LINES = {
    "none": "",
    "thin": "Use thin, delicate outlines.",
    "bold": "Use thick, confident outlines.",
}
QUALITIES = {"low", "medium"}  # "high" deliberately left out to protect the budget

IDENTITY_RULES = (
    "IDENTITY IS THE TOP PRIORITY. The character must be instantly recognizable as the "
    "person in the reference photo: keep the same face shape, jawline, eye shape and spacing, "
    "eye color, nose shape, mouth and lips, eyebrows, ears, skin tone, hairline, hair color, "
    "hair texture, hair length and hairstyle, facial hair, glasses, freckles, moles, and any "
    "other distinctive marks exactly as in the photo. Do not change apparent age, gender, "
    "body type, or ethnicity. Do not beautify, smooth away features, or swap in a generic face."
)

# ---------------------------------------------------------------------------
# Scene options. The scene specification is assembled from these and is used, word for word,
# both in the prompt and as the caption. Each scene also has a checklist used by /api/check.
# ---------------------------------------------------------------------------
TIMES = {
    "morning": "on a bright sunny morning",
    "golden": "in warm golden-hour sunset light",
    "dawn": "at misty dawn with soft pink light",
    "storm": "under dark gathering storm clouds",
}
EXPRESSIONS = {
    "hopeful": "a hopeful, curious smile",
    "excited": "a wide, excited grin",
    "determined": "a determined, focused look",
    "nervous": "a nervous, wide-eyed look",
}
OUTFITS = {
    "peasant": ("a patched linen shirt, a brown wool vest, and rough trousers",
                "wearing a patched linen shirt and brown vest"),
    "overalls": ("faded blue farm overalls over a plain shirt",
                 "wearing farm overalls"),
    "own": ("the same clothes the person is wearing in the photo",
            "wearing the same clothes as in the photo"),
    "royal": ("a too-big hand-me-down velvet cloak over simple farm clothes",
              "wearing a velvet cloak over farm clothes"),
}


def build_scene(scene_id, opts):
    """Return (spec, checklist). spec is the exact text sent and shown as the caption."""
    time_txt = TIMES[opts["time"]]
    expr = EXPRESSIONS[opts["expression"]]
    outfit_desc, outfit_check = OUTFITS[opts["outfit"]]
    extra = opts["extra"]

    if scene_id == "planting":
        spec = (
            f"Jack, wearing {outfit_desc}, kneels in a freshly dug garden row beside his small "
            f"thatched cottage {time_txt}. With {expr}, he presses three glowing magic beans into "
            "the dark soil with his fingertips. A small open cloth pouch lies by his knee and a "
            "watering can stands nearby. No beanstalk has grown yet - only bare soil."
        )
        checklist = [
            "Jack is kneeling",
            "Jack is putting beans into soil with his hand",
            "a freshly dug garden row / bare soil",
            "a small thatched cottage",
            "an open cloth pouch near Jack",
            "a watering can",
            "NO beanstalk anywhere in the image",
            f"lighting/time: {opts['time']}",
            f"Jack {outfit_check}",
        ]
        if extra:
            spec += " Jack's mother watches from the cottage doorway, arms crossed."
            checklist.append("Jack's mother in the cottage doorway")
    else:
        spec = (
            f"Jack, wearing {outfit_desc}, climbs hand over hand up an enormous twisting green "
            f"beanstalk {time_txt}, both hands gripping a thick vine and one foot braced on a broad "
            f"leaf. He looks up toward the clouds just above him with {expr}; his tiny thatched "
            "cottage and fields are far below."
        )
        checklist = [
            "an enormous green beanstalk",
            "Jack is climbing it, gripping the vine with both hands",
            "one foot on a broad leaf",
            "Jack is looking upward",
            "clouds just above Jack",
            "a tiny cottage and fields far below",
            f"lighting/time: {opts['time']}",
            f"Jack {outfit_check}",
        ]
        if extra:
            spec += " The turrets of the giant's castle peek out of the clouds above."
            checklist.append("a castle in the clouds above")
    checklist.append(f"Jack's facial expression: {opts['expression']}")
    return spec, checklist


def read_settings(form):
    s = {
        "style": form.get("style", "storybook3d"),
        "exaggeration": form.get("exaggeration", "moderate"),
        "palette": form.get("palette", "vivid"),
        "lines": form.get("lines", "none"),
        "quality": form.get("quality", "low"),
    }
    if (s["style"] not in STYLES or s["exaggeration"] not in EXAGGERATION or s["palette"] not in PALETTES
            or s["lines"] not in LINES or s["quality"] not in QUALITIES):
        raise ValueError("Invalid cartoon setting.")
    return s


def read_scene_opts(form):
    o = {
        "time": form.get("time", "morning"),
        "expression": form.get("expression", "hopeful"),
        "outfit": form.get("outfit", "peasant"),
        "extra": form.get("extra") == "1",
    }
    if o["time"] not in TIMES or o["expression"] not in EXPRESSIONS or o["outfit"] not in OUTFITS:
        raise ValueError("Invalid scene option.")
    return o


def style_sentence(s):
    return (f"Art style: {STYLES[s['style']]}, {PALETTES[s['palette']]}. "
            f"{EXAGGERATION[s['exaggeration']]} {LINES[s['lines']]}").strip()


def cartoon_prompt(s):
    return (
        "Turn the person in this photo into a cartoon character portrait. "
        f"{style_sentence(s)} {IDENTITY_RULES} "
        "Head-and-shoulders, facing the viewer, neutral friendly expression, plain light background, no text."
    )


def scene_prompt(spec, s):
    return (
        "Image 1 is a cartoon character; image 2 is the real photo of the same person. "
        "Draw this exact character as Jack in a Jack and the Beanstalk storybook illustration. "
        f"{style_sentence(s)} Match the character design in image 1 and the real facial features "
        f"in image 2. {IDENTITY_RULES} "
        "Jack's face must be clearly visible, unobstructed, turned at least partly toward the viewer, "
        "and large enough to recognize (not a tiny distant figure). "
        f"SCENE - depict every element of this description exactly, and nothing that contradicts it: {spec} "
        "Frame the shot wide enough to include every scene element. No text, captions, or speech bubbles."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_png(raw: bytes, name: str, max_side=1024) -> tuple:
    """Fix phone rotation, convert to RGB PNG, cap size to keep input cost low."""
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise ValueError("That file isn't a readable image (use JPG, PNG, or WEBP).")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return (name, buf.getvalue(), "image/png")


def uploaded_photo():
    f = request.files.get("photo")
    if not f or not f.filename:
        raise ValueError("Please upload or take a photo.")
    return to_png(f.read(), "photo.png")


def decode_b64(b64, what):
    if not b64:
        raise ValueError(f"Missing {what}.")
    try:
        return base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError(f"The {what} was corrupted; generate it again.")


_hits = defaultdict(deque)
LIMIT, WINDOW = int(os.environ.get("HOURLY_LIMIT", "40")), 3600


def rate_limited():
    """Tiny per-IP limiter so a public URL can't drain the balance."""
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
    extra = {}
    # input_fidelity="high" preserves faces better, but gpt-image-1-mini rejects it.
    # It is only sent to models that support it (e.g. IMAGE_MODEL=gpt-image-1).
    if "mini" not in IMAGE_MODEL:
        extra["input_fidelity"] = "high"
    result = client().images.edit(
        model=IMAGE_MODEL,
        image=images,
        prompt=prompt,
        quality=quality,
        size=size,
        n=1,
        **extra,
    )
    return result.data[0].b64_json


def error(msg, code=400):
    return jsonify({"error": msg}), code


def api_error(e):
    app.logger.exception("API call failed")
    msg = getattr(e, "message", None) or str(e)
    if "safety" in msg.lower() or "moderation" in msg.lower():
        msg = "The image service declined this photo. Try a different, clearly lit face photo."
    elif "verif" in msg.lower():
        msg = "Your OpenAI organization must be verified to use image models (platform.openai.com → Settings → Organization)."
    return error(f"Generation failed: {msg}", 502)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def health():
    return "ok"


@app.post("/api/cartoonify")
def cartoonify():
    if rate_limited():
        return error("Hourly limit reached — try again later.", 429)
    try:
        photo = uploaded_photo()
        s = read_settings(request.form)
    except ValueError as e:
        return error(str(e))
    try:
        return jsonify({"image": call_edit(photo, cartoon_prompt(s), s["quality"], "1024x1024")})
    except Exception as e:
        return api_error(e)


@app.post("/api/scene")
def scene():
    if rate_limited():
        return error("Hourly limit reached — try again later.", 429)
    try:
        scene_id = request.form.get("scene")
        if scene_id not in ("planting", "climbing"):
            raise ValueError("Unknown scene.")
        photo = uploaded_photo()
        cartoon = to_png(decode_b64(request.form.get("cartoon"), "cartoon"), "cartoon.png")
        s = read_settings(request.form)
        spec, checklist = build_scene(scene_id, read_scene_opts(request.form))
    except ValueError as e:
        return error(str(e))
    size = "1024x1536" if scene_id == "climbing" else "1536x1024"
    try:
        b64 = call_edit([cartoon, photo], scene_prompt(spec, s), s["quality"], size)
    except Exception as e:
        return api_error(e)
    # The caption is the scene specification exactly as sent to the model.
    return jsonify({"image": b64, "caption": spec, "checklist": checklist})


LIKENESS_ITEMS = [
    "Hair color matches",
    "Hair length and style match",
    "Skin tone matches",
    "Glasses match (present in both or absent in both)",
    "Facial hair matches (present in both or absent in both)",
    "Face shape and proportions are similar",
    "Eyebrows, eyes, nose and mouth have similar shapes",
    "Apparent age range matches",
]


def data_url(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode()


@app.post("/api/check")
def check():
    """ONE vision call that grades a generated scene on both production requirements:
    (1) likeness: does the character share the visible features of the person in the photo?
    (2) fidelity: is every element of the caption visible?"""
    if rate_limited():
        return error("Hourly limit reached — try again later.", 429)
    try:
        photo = uploaded_photo()[1]
        scene_png = to_png(decode_b64(request.form.get("image"), "image"), "scene.png", max_side=1024)[1]
        photo = to_png(photo, "photo.png", max_side=768)[1]
        spec = str(request.form.get("caption", ""))[:2000]
        items = [str(x)[:200] for x in json.loads(request.form.get("checklist") or "[]")][:15]
        if not spec or not items:
            raise ValueError("Nothing to check.")
    except (ValueError, json.JSONDecodeError) as e:
        return error(str(e) or "Bad check request.")
    scene_list = "\n".join(f"S{i + 1}. {t}" for i, t in enumerate(items))
    like_list = "\n".join(f"L{i + 1}. {t}" for i, t in enumerate(LIKENESS_ITEMS))
    instructions = (
        "You are a strict QA reviewer for a personalized storybook app. Image 1 is the user's own photo, "
        "which they uploaded so their likeness could be drawn as the cartoon character Jack. Image 2 is "
        "the generated illustration. Do not identify anyone; only compare visible features.\n\n"
        "PART A - scene fidelity. The illustration must match this caption:\n"
        f"\"{spec}\"\nFor each item, is it clearly visible in image 2?\n{scene_list}\n\n"
        "PART B - likeness. Compare the main character in image 2 with the person in image 1, allowing "
        "for cartoon stylization.\n"
        f"{like_list}\n\n"
        "Also give likeness_score 1-10: would a friend of the person in image 1 recognize them as the "
        "character in image 2?\n\n"
        'Reply with JSON only: {"items":[{"item":"<S text>","pass":true,"note":"<max 12 words>"}],'
        '"likeness":[{"item":"<L text>","pass":true,"note":"<max 12 words>"}],'
        '"likeness_score":7,"verdict":"<one sentence overall>"}'
    )
    try:
        resp = client().chat.completions.create(
            model=CHECK_MODEL,
            response_format={"type": "json_object"},
            max_tokens=1100,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": instructions},
                {"type": "image_url", "image_url": {"url": data_url(photo), "detail": "high"}},
                {"type": "image_url", "image_url": {"url": data_url(scene_png), "detail": "high"}},
            ]}],
        )
        result = json.loads(resp.choices[0].message.content)
    except Exception as e:
        return api_error(e)
    return jsonify(result)


@app.errorhandler(413)
def too_big(_):
    return error("That request was too large. Try a smaller photo (under about 10 MB).", 413)


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
