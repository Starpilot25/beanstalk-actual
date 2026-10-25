"""
PDF layer: full-bleed art, story text drawn on top in a real font (never by the image model),
and an About Me page at the end. Pure Python (reportlab); no API calls.
"""

import io
import os

from PIL import Image
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("YoungSerif", os.path.join(FONT_DIR, "YoungSerif-Regular.ttf")))
FONT = "YoungSerif"

# Landscape page with the same 3:2 shape as the 1536x1024 art (11 x 7.33 inches).
W, H = 792, 528
MARGIN = 54

INK = HexColor("#1f2a22")
PAPER = HexColor("#fbf6ea")
LEAF = HexColor("#24613a")


def _with_fade(im, zone, dark):
    """Bake a smooth gradient into the art behind the text so it reads on any picture."""
    import numpy as np
    a = np.asarray(im).astype("float32")
    h = a.shape[0]
    band = int(h * 0.38)
    t = np.zeros(h, dtype="float32")
    ramp = (1 - np.linspace(0, 1, band)) ** 1.6 * (0.62 if dark else 0.55)
    if zone == "bottom":
        t[h - band:] = ramp[::-1]
    else:
        t[:band] = ramp
    tint = np.array([14, 16, 22] if dark else [255, 255, 255], dtype="float32")
    a = a * (1 - t[:, None, None]) + tint * t[:, None, None]
    return Image.fromarray(a.clip(0, 255).astype("uint8"))


def _balanced_lines(text, size, max_w):
    """Wrap into as few lines as fit, with line widths as even as possible."""
    words = text.split()
    lines = simpleSplit(text, FONT, size, max_w)
    if len(lines) != 2:
        return lines
    best = None
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        wa, wb = pdfmetrics.stringWidth(a, FONT, size), pdfmetrics.stringWidth(b, FONT, size)
        if max(wa, wb) <= max_w and (best is None or max(wa, wb) < best[0]):
            best = (max(wa, wb), [a, b])
    return best[1] if best else lines


def _story_text(c, text, zone, dark):
    size = 30
    max_w = W - 2 * MARGIN - 80
    lines = _balanced_lines(text, size, max_w)
    while len(lines) > 2 and size > 20:
        size -= 2
        lines = _balanced_lines(text, size, max_w)
    lead = size * 1.3
    block = lead * len(lines)
    if zone == "bottom":
        y = MARGIN + block - lead + size * 0.2
    else:
        y = H - MARGIN - size
    c.setFont(FONT, size)
    for line in lines:
        if dark:  # light lettering on a dark fade: a faint shadow helps
            c.setFillColor(Color(0, 0, 0, 0.45))
            c.drawCentredString(W / 2 + 1.2, y - 1.2, line)
            c.setFillColor(HexColor("#fffaf0"))
        else:
            c.setFillColor(INK)
        c.drawCentredString(W / 2, y, line)
        y -= lead


def _page_number(c, n, dark):
    c.setFont(FONT, 11)
    c.setFillColor(Color(1, 1, 1, 0.8) if dark else Color(0.12, 0.16, 0.13, 0.7))
    c.drawRightString(W - 22, 16, str(n))


def _cover_fit(img_bytes, zone, dark):
    """Crop to exactly 3:2 so the art fills the page edge to edge, then add the text fade."""
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    target = W / H
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / h < target:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return ImageReader(_with_fade(im, zone, dark))


def _about_page(c, name, about, hero_img):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    left = MARGIN
    text_x = left
    if hero_img:
        im = Image.open(io.BytesIO(hero_img)).convert("RGB")
        ph = H - 2 * MARGIN
        pw = ph * im.width / im.height
        c.saveState()
        p = c.beginPath()
        p.roundRect(left, MARGIN, pw, ph, 18)
        c.clipPath(p, stroke=0, fill=0)
        c.drawImage(ImageReader(im), left, MARGIN, pw, ph)
        c.restoreState()
        text_x = left + pw + 40
    width = W - text_x - MARGIN
    y = H - MARGIN - 20
    c.setFillColor(LEAF)
    c.setFont(FONT, 16)
    c.drawString(text_x, y, "About me")
    y -= 50
    c.setFillColor(INK)
    size = 40
    while c.stringWidth(name, FONT, size) > width and size > 22:
        size -= 2
    c.setFont(FONT, size)
    c.drawString(text_x, y, name)
    y -= 30
    if about.get("age"):
        c.setFont(FONT, 15)
        c.setFillColor(HexColor("#4c5d51"))
        c.drawString(text_x, y, f"Age {about['age']}")
        y -= 20
    for label, key in (("Things I love", "likes"), ("All about me", "about")):
        val = about.get(key)
        if not val:
            continue
        y -= 22
        c.setFillColor(LEAF)
        c.setFont(FONT, 13)
        c.drawString(text_x, y, label)
        y -= 22
        c.setFillColor(INK)
        c.setFont(FONT, 14)
        for para in val.splitlines():
            for line in simpleSplit(para, FONT, 14, width) or [""]:
                if y < MARGIN:
                    return
                c.drawString(text_x, y, line)
                y -= 20


def build_pdf(pages, images, name, about, hero_img=None):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Jack and the Beanstalk")
    c.setAuthor(name)
    for p in pages:
        dark = p["text_color"] == "light"
        c.drawImage(_cover_fit(images[p["n"]], p["zone"], dark), 0, 0, W, H)
        _story_text(c, p["text"], p["zone"], dark)
        _page_number(c, p["n"], dark)
        c.showPage()
    _about_page(c, name, about, hero_img)
    c.showPage()
    c.save()
    return buf.getvalue()
