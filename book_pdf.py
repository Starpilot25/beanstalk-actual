"""
PDF layer: 20 story pages laid out by the shared TEMPLATE, then an About Me page. Pure Python (reportlab).

The image model never draws words. Every word here is real type (Young Serif), placed in one of two ways:
  full   - the art fills the page; the words sit in the band (top, middle or bottom third) that the analysis
           found empty of faces and important things, over a soft shade that keeps them legible.
  below  - the art sits in a frame on the upper part of the page and the words go on the paper beneath it,
           so they cannot cover anything. Used by "framed" pages, and by any page with no clear band.
"""
import io
import os
import tempfile
import threading

import numpy as np
from PIL import Image
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import stories as S

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("YoungSerif", os.path.join(FONT_DIR, "YoungSerif-Regular.ttf")))
FONT = "YoungSerif"

W, H = 792, 528          # landscape, 11 x 7.33 in, the same 3:2 shape as the 1536x1024 art
MARGIN = 40
INK = HexColor("#1f2a22")
PAPER = HexColor("#fbf6ea")
LEAF = HexColor("#24613a")
BAND = {"top": (2 / 3, 1.0), "middle": (1 / 3, 2 / 3), "bottom": (0.0, 1 / 3)}   # PDF y-fractions (0 = bottom)


def _curly(text):
    """Typeset quotes: "x" -> “x”, it's -> it’s."""
    out, open_q = [], True
    for i, ch in enumerate(text):
        if ch == '"':
            out.append("\u201c" if open_q else "\u201d")
            open_q = not open_q
        elif ch == "'":
            out.append("\u2019" if i and text[i - 1].isalnum() else "\u2018")
        else:
            out.append(ch)
    return "".join(out)


def _lines(text, size, max_w):
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


def _fit(text, max_w, max_h, start=28, smallest=15):
    size = start
    while True:
        lines = _lines(text, size, max_w)
        if (len(lines) <= 3 and len(lines) * size * 1.3 <= max_h) or size <= smallest:
            return size, lines
        size -= 1


def _crop32(raw):
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = im.size
    t = W / H
    if w / h > t:
        nw = int(h * t)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    elif w / h < t:
        nh = int(w / t)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    return im


def _shade_alpha(zone, steps=120):
    """How dark the shade is at each of `steps` horizontal strips, bottom to top (0..1). The words' band is
    darkest at the page edge, so white type reads on anything."""
    y = (np.arange(steps) + 0.5) / steps            # 0 = bottom of the page, 1 = top
    a = np.zeros(steps)
    third, pad = 1 / 3, 40 / 1024                    # same shape as the old pixel mask on the 1024px art
    if zone == "top":
        lo = 1 - third - pad
        m = y >= lo
        a[m] = (0.62 * (y[m] - lo) / (1 - lo)) ** 1.2
    elif zone == "bottom":
        hi = third + pad
        m = y <= hi
        a[m] = (0.62 * (hi - y[m]) / hi) ** 1.2
    else:
        lo, hi = third - pad, 2 * third + pad
        m = (y >= lo) & (y <= hi)
        x = (y[m] - lo) / (hi - lo) * 2 - 1
        a[m] = 0.5 * np.exp(-(x ** 2) / 0.35)
    return a


_SHADES = {}


def _draw_shade(c, zone):
    """Lay the shade over the picture as a tiny see-through image (1 x 256 pixels) stretched across the page.
    Doing it in the picture's own pixels meant decoding, blending and re-encoding every 1536px picture, about
    18 s a book on the 0.1-CPU server; this costs nothing."""
    if zone not in _SHADES:
        a = _shade_alpha(zone, 256)[::-1]           # image rows run top to bottom
        rgba = np.zeros((256, 1, 4), dtype="uint8")
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 12, 16, 24
        rgba[..., 3] = (a * 255).round().astype("uint8").reshape(256, 1)
        _SHADES[zone] = ImageReader(Image.fromarray(rgba, "RGBA"))
    c.drawImage(_SHADES[zone], 0, 0, W, H, mask="auto")


_tls = threading.local()


def _path(raw):
    """A JPEG file for the PDF to embed as it is. The art is already 3:2 JPEG, so it is written straight to disk
    with no decoding at all; anything else is cropped and saved once."""
    _tls.n = getattr(_tls, "n", 0) + 1
    path = os.path.join(_tls.dir, f"{_tls.n}.jpg")
    im = Image.open(io.BytesIO(raw))                 # reads the header only
    if im.format == "JPEG" and im.mode == "RGB" and abs(im.width / im.height - W / H) < 0.005:
        with open(path, "wb") as f:
            f.write(raw)
        return path
    return _jpeg(_crop32(raw))


def _jpeg(im):
    """Save a picture as a JPEG file and hand the PDF its path: the PDF embeds the JPEG bytes as they are, rather
    than re-compressing pixels (about 100 s and 300 MB+ for a book on the slow server)."""
    _tls.n = getattr(_tls, "n", 0) + 1
    path = os.path.join(_tls.dir, f"{_tls.n}.jpg")
    im.save(path, "JPEG", quality=90)
    return path


def _full_page(c, raw, text, zone, n):
    c.drawImage(_path(raw), 0, 0, W, H)
    _draw_shade(c, zone)
    lo, hi = BAND[zone]
    band_bottom, band_h = lo * H, (hi - lo) * H
    size, lines = _fit(text, W - 2 * MARGIN - 60, band_h - 36)
    lead = size * 1.3
    block = lead * len(lines)
    # Keep the block inside its band: hug the page edge for top/bottom, centre it for middle.
    if zone == "top":
        y = H - 30 - size
    elif zone == "bottom":
        y = 30 + block - lead + size * 0.15
    else:
        y = band_bottom + band_h / 2 + block / 2 - size
    c.setFont(FONT, size)
    for line in lines:
        c.setFillColor(Color(0, 0, 0, 0.5))
        c.drawCentredString(W / 2 + 1.2, y - 1.2, line)
        c.setFillColor(HexColor("#fffaf0"))
        c.drawCentredString(W / 2, y, line)
        y -= lead
    _number(c, n, light=True)


def _below_page(c, raw, text, n):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    text_h = 118
    ah = H - text_h - 2 * 22
    aw = ah * 1.5
    x, y = (W - aw) / 2, text_h + 22
    c.saveState()
    p = c.beginPath()
    p.roundRect(x, y, aw, ah, 14)
    c.clipPath(p, stroke=0, fill=0)
    c.drawImage(_path(raw), x, y, aw, ah)
    c.restoreState()
    c.setStrokeColor(HexColor("#c9a24a"))
    c.setLineWidth(2)
    c.roundRect(x, y, aw, ah, 14, stroke=1, fill=0)
    size, lines = _fit(text, W - 2 * MARGIN - 40, text_h - 24, start=24)
    lead = size * 1.3
    ty = text_h / 2 + (lead * len(lines)) / 2 - size * 0.9
    c.setFont(FONT, size)
    c.setFillColor(INK)
    for line in lines:
        c.drawCentredString(W / 2, ty, line)
        ty -= lead
    _number(c, n, light=False)


def _number(c, n, light):
    c.setFont(FONT, 11)
    c.setFillColor(Color(1, 1, 1, 0.85) if light else Color(0.12, 0.16, 0.13, 0.7))
    c.drawRightString(W - 18, 12, str(n))


def _about(c, book, hero):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    text_x = MARGIN + 10
    if hero:
        im = Image.open(io.BytesIO(hero)).convert("RGB")
        if im.width > im.height * 1.2:          # the hero sheet: the close-up face is its left half
            im = im.crop((0, 0, im.width // 2, im.height))
        ph = H - 2 * MARGIN
        pw = ph * im.width / im.height
        c.saveState()
        p = c.beginPath()
        p.roundRect(MARGIN, MARGIN, pw, ph, 18)
        c.clipPath(p, stroke=0, fill=0)
        c.drawImage(_jpeg(im), MARGIN, MARGIN, pw, ph)
        c.restoreState()
        text_x = MARGIN + pw + 40
    width = W - text_x - MARGIN
    name = book.get("child_name") or "Me"
    y = H - MARGIN - 24
    c.setFillColor(LEAF)
    c.setFont(FONT, 16)
    c.drawString(text_x, y, "About me")
    y -= 50
    size = 40
    while c.stringWidth(name, FONT, size) > width and size > 22:
        size -= 2
    c.setFillColor(INK)
    c.setFont(FONT, size)
    c.drawString(text_x, y, name)
    y -= 30
    if book.get("age"):
        c.setFont(FONT, 15)
        c.setFillColor(HexColor("#4c5d51"))
        c.drawString(text_x, y, f"Age {book['age']}")
        y -= 20
    for label, key in (("Things I love", "likes"), ("All about me", "about")):
        val = book.get(key)
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
    c.setFont(FONT, 11)
    c.setFillColor(Color(0.12, 0.16, 0.13, 0.6))
    c.drawString(text_x, MARGIN, f"Starring in {S.STORIES[book['story']]['title']}")


def _cover(c, raw, title, name, zone):
    """Front cover: the art full-bleed, the title and the child's name in the clear sky at the top."""
    starring = f"starring {name}" if name else ""
    if zone != "top":                        # sky wasn't clear: frame the art and put the title on paper
        c.setFillColor(LEAF)
        c.rect(0, 0, W, H, stroke=0, fill=1)
        aw, ah = W - 120, (W - 120) / 1.5 * 0.82
        x, y = 60, 40
        c.drawImage(_path(raw), x, y, aw, ah, preserveAspectRatio=True, anchor="c")
        ty = H - 70
    else:
        c.drawImage(_path(raw), 0, 0, W, H)
        _draw_shade(c, "top")
        ty = H - 74
    size = 46
    while pdfmetrics.stringWidth(title, FONT, size) > W - 120 and size > 28:
        size -= 2
    c.setFont(FONT, size)
    c.setFillColor(Color(0, 0, 0, 0.45))
    c.drawCentredString(W / 2 + 2, ty - 2, title)
    c.setFillColor(HexColor("#ffe9a8"))
    c.drawCentredString(W / 2, ty, title)
    if starring:
        c.setFont(FONT, 20)
        c.setFillColor(Color(0, 0, 0, 0.45))
        c.drawCentredString(W / 2 + 1.5, ty - 38 - 1.5, starring)
        c.setFillColor(HexColor("#fffaf0"))
        c.drawCentredString(W / 2, ty - 38, starring)


def build_book(story, images, hero, book):
    """images: {n: (jpeg_bytes, zone)}. Returns PDF bytes: cover, 20 story pages, About Me."""
    with tempfile.TemporaryDirectory() as d:
        _tls.dir, _tls.n = d, 0
        return _build(story, images, hero, book)


def _build(story, images, hero, book):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle(S.STORIES[story]["title"])
    c.setAuthor(book.get("child_name") or "")
    if 0 in images:
        raw, zone = images[0]
        _cover(c, raw, S.STORIES[story]["title"], book.get("child_name") or "", zone)
        c.showPage()
    for p in S.STORIES[story]["pages"]:
        raw, zone = images[p["n"]]
        if zone in BAND:
            _full_page(c, raw, _curly(p["text"]), zone, p["n"])
        else:
            _below_page(c, raw, _curly(p["text"]), p["n"])
        c.showPage()
    _about(c, book, hero)
    c.showPage()
    c.save()
    return buf.getvalue()
