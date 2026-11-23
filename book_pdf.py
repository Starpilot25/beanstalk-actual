"""
PDF layer, pure Python (reportlab). Two outputs from the same page designs:

  build_book          the downloadable PDF: front cover ("Title, starring Name"), copyright page, the 20 story
                      pages laid out by the shared TEMPLATE, and the About Me back cover.
  build_print_*       the files a print shop needs (Lulu): an interior PDF (title page, copyright page, story
                      pages 1-20, The End, padded to a multiple of 4) and a one-page cover spread (back cover About
                      Me + front cover), at the printed trim size with 1/8 inch bleed.

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
from reportlab import rl_config

# Embed the JPEGs as raw binary. reportlab's default wraps every image in ASCII85 text, done in pure Python here:
# about 3.4 s a book on a laptop and ~15 s on the 0.1-CPU server, and a PDF 25% bigger. Binary: 0.1 s.
rl_config.useA85 = 0

import stories as S
from contextlib import contextmanager
from datetime import date

PUBLISHER = os.environ.get("PUBLISHER", "Beanstalk Books")
PUBLISHER_PLACE = os.environ.get("PUBLISHER_PLACE", "New York, NY")

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
    c.drawRightString(W - 40, 14, str(n))      # inside the printer's half-inch safety margin


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



def _copyright(c, story, book):
    """The copyright page: publisher, notice, and what the book is. The story starts on the page after this."""
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    title = S.STORIES[story]["title"]
    name = book.get("child_name") or ""
    x, y = 120, H - 150
    width = W - 240
    c.setFillColor(INK)
    c.setFont(FONT, 18)
    c.drawString(x, y, f"{title}, starring {name}" if name else title)
    y -= 34
    made = book.get("done_at") or book.get("started_at")
    when = date.fromtimestamp(made) if made else date.today()
    paras = [
        f"Text and illustrations copyright \u00a9 {when.year} {PUBLISHER}. All rights reserved. No part of this book "
        f"may be reproduced in any form without written permission from the publisher.",
        f"Published by {PUBLISHER}, {PUBLISHER_PLACE}.",
        "The story is retold from the traditional fairy tale. The pictures were made with the help of AI from a "
        "photograph supplied by the person who ordered this book.",
        f"Made especially for {name or 'you'}. First edition, {when.strftime('%B %Y')}."
        + (f" Book no. {book['id']}." if book.get("id") else ""),
    ]
    c.setFont(FONT, 11.5)
    c.setFillColor(HexColor("#4c5d51"))
    for para in paras:
        for line in simpleSplit(para, FONT, 11.5, width):
            c.drawString(x, y, line)
            y -= 17
        y -= 10
    c.setFillColor(LEAF)
    c.setFont(FONT, 15)
    c.drawString(x, 110, PUBLISHER)
    c.setStrokeColor(LEAF)
    c.setLineWidth(1)
    c.line(x, 102, x + c.stringWidth(PUBLISHER, FONT, 15), 102)


def _title_page(c, story, book):
    """The printed book's first inside page (the right-hand page you see on opening it)."""
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    title = S.STORIES[story]["title"]
    size = 44
    while c.stringWidth(title, FONT, size) > W - 160 and size > 26:
        size -= 2
    c.setFillColor(INK)
    c.setFont(FONT, size)
    c.drawCentredString(W / 2, H / 2 + 30, title)
    if book.get("child_name"):
        c.setFont(FONT, 22)
        c.setFillColor(LEAF)
        c.drawCentredString(W / 2, H / 2 - 16, f"starring {book['child_name']}")
    c.setFont(FONT, 13)
    c.setFillColor(HexColor("#4c5d51"))
    c.drawCentredString(W / 2, 70, PUBLISHER)


def _the_end(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont(FONT, 40)
    c.drawCentredString(W / 2, H / 2 - 10, "The End")


def _blank(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)


def _story_page(c, p, images):
    raw, zone = images[p["n"]]
    if zone in BAND:
        _full_page(c, raw, _curly(p["text"]), zone, p["n"])
    else:
        _below_page(c, raw, _curly(p["text"]), p["n"])


def build_book(story, images, hero, book):
    """images: {n: (jpeg_bytes, zone)}. Returns PDF bytes: cover, copyright page, 20 story pages, About Me back
    cover."""
    with _geo_lock, tempfile.TemporaryDirectory() as d:
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
    _copyright(c, story, book)
    c.showPage()
    for p in S.STORIES[story]["pages"]:
        _story_page(c, p, images)
        c.showPage()
    _about(c, book, hero)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------------
# Print files (Lulu). Trim 11 x 8.5 in landscape; every page gets 1/8 inch (9 pt) bleed on each side.
# The on-screen pages are 3:2; the printed page is 11 x 8.5. Rather than crop the art (and risk cutting a face at
# the edge), each inside page is drawn at full printed width and centred on cream paper: the art bleeds off the
# sides, with a cream band top and bottom. Every word stays at least half an inch inside the trim.
# ---------------------------------------------------------------------------------------------------------
TRIM_W, TRIM_H, BLEED = 11 * 72, 8.5 * 72, 9
PW, PH = TRIM_W + 2 * BLEED, TRIM_H + 2 * BLEED
_geo_lock = threading.RLock()   # every build holds it, so no build ever sees another's page size


@contextmanager
def _geometry(w, h):
    """Draw with the page functions at another page size (they read the module's W and H)."""
    global W, H
    with _geo_lock:
        old = W, H
        W, H = w, h
        try:
            yield
        finally:
            W, H = old


def _placed(c, draw, x0, area_w, area_h):
    """Draw a 792x528 page design scaled to area_w wide, centred vertically on cream paper."""
    c.setFillColor(PAPER)
    c.rect(x0, 0, area_w, area_h, stroke=0, fill=1)
    k = area_w / W
    c.saveState()
    c.translate(x0, (area_h - H * k) / 2)
    c.scale(k, k)
    draw()
    c.restoreState()


def interior_page_count():
    n = 2 + len(S.TEMPLATE) + 1                      # title, copyright, story, The End
    return n + (-n) % 4                              # saddle stitch / casewrap want a multiple of 4


def build_print_interior(story, images, hero, book):
    with _geo_lock, tempfile.TemporaryDirectory() as d:
        _tls.dir, _tls.n = d, 0
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(PW, PH))
        c.setTitle(f"{S.STORIES[story]['title']} (interior)")
        pages = [lambda: _title_page(c, story, book), lambda: _copyright(c, story, book)]
        pages += [(lambda p=p: _story_page(c, p, images)) for p in S.STORIES[story]["pages"]]
        pages.append(lambda: _the_end(c))
        while len(pages) < interior_page_count():
            pages.append(lambda: _blank(c))
        for draw in pages:
            _placed(c, draw, 0, PW, PH)
            c.showPage()
        c.save()
        return buf.getvalue()


def build_print_cover(story, images, hero, book, spread_w=None, spread_h=None):
    """One page, laid flat: back cover (About Me) on the left, the spine, the front cover on the right.
    spread_w/h come from the printer's cover-dimensions API. For a hardcover (casewrap) the sheet is bigger than the
    two covers: a margin all round wraps around the boards, and the spine sits between them. Everything that must be
    seen is drawn inside the trim of each cover; the wrap margin and the spine are the night-sky colour."""
    sh = spread_h or PH
    margin = (sh - TRIM_H) / 2                       # bleed (paperback) or bleed + wrap (hardcover), each edge
    sw = spread_w or (2 * TRIM_W + 2 * margin)
    spine = max(0.0, sw - 2 * TRIM_W - 2 * margin)
    back_x, front_x = margin, margin + TRIM_W + spine
    with _geo_lock, tempfile.TemporaryDirectory() as d:
        _tls.dir, _tls.n = d, 0
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(sw, sh))
        c.setTitle(f"{S.STORIES[story]['title']}, starring {book.get('child_name') or ''} (cover)")
        c.setFillColor(HexColor("#0e2a50"))          # the cloth-coloured wrap and spine
        c.rect(0, 0, sw, sh, stroke=0, fill=1)
        raw, zone = images[0]
        c.saveState()                                # front cover: the art fills the trim, title and name on it
        c.translate(front_x, margin)
        with _geometry(TRIM_W, TRIM_H):
            _cover(c, raw, S.STORIES[story]["title"], book.get("child_name") or "", zone)
        c.restoreState()
        c.saveState()                                # back cover: About Me, on cream paper
        c.translate(back_x, margin)
        _placed(c, lambda: _about(c, book, hero), 0, TRIM_W, TRIM_H)
        c.restoreState()
        if spine >= 30:                              # wide enough to read: the title down the spine
            c.saveState()
            c.translate(front_x - spine / 2 + 4, sh / 2)
            c.rotate(-90)
            c.setFillColor(HexColor("#fff3cf"))
            c.setFont(FONT, min(12, spine * 0.45))
            c.drawCentredString(0, 0, S.STORIES[story]["title"])
            c.restoreState()
        c.showPage()
        c.save()
        return buf.getvalue()


def build_print_preview(story, images, hero, book):
    """What the customer approves: the printed book page by page, at its printed size (front cover, the 24 inside
    pages, back cover), with the same drawing code as the files sent to the printer."""
    half = TRIM_W + BLEED
    with _geo_lock, tempfile.TemporaryDirectory() as d:
        _tls.dir, _tls.n = d, 0
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(half, PH))
        c.setTitle(f"{S.STORIES[story]['title']}, starring {book.get('child_name') or ''} (print proof)")
        raw, zone = images[0]
        with _geometry(half, PH):
            _cover(c, raw, S.STORIES[story]["title"], book.get("child_name") or "", zone)
        c.showPage()
        pages = [lambda: _title_page(c, story, book), lambda: _copyright(c, story, book)]
        pages += [(lambda p=p: _story_page(c, p, images)) for p in S.STORIES[story]["pages"]]
        pages.append(lambda: _the_end(c))
        while len(pages) < interior_page_count():
            pages.append(lambda: _blank(c))
        for draw in pages:
            c.setPageSize((PW, PH))
            _placed(c, draw, 0, PW, PH)
            c.showPage()
        c.setPageSize((half, PH))
        _placed(c, lambda: _about(c, book, hero), 0, half, PH)
        c.showPage()
        c.save()
        return buf.getvalue()
