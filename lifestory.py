"""
Life stories: upload pages about one person, and get a children's life story written only from those pages.

  1. Read:     files (PDF, HTML, EPUB, Word, text) or links (Project Gutenberg book pages work as they are).
  2. Chunk:    ~1,000-character pieces cut at sentence ends, with one sentence of overlap; each remembers its page.
  3. Embed:    OpenAI text-embedding-3-small (512 numbers per chunk), stored in the database next to the text.
  4. Retrieve: each of the 20 questions is matched two ways, by meaning (embeddings) and by words (BM25), and the
               two rankings are merged; the top 8 chunks go to the model.
  5. Answer:   the model answers each question from those 8 chunks only, citing a chunk id and an exact quote for
               every fact, or says "not in the sources". Quotes are checked word for word against the chunk.
  6. Story:    a second call writes the story from the checked facts only; every sentence lists its facts.
  7. Check:    every sentence is sent back with the chunks it cites, and a third call marks anything the chunks
               don't say (which can only have come from the model's own training). Those sentences are rewritten
               from the chunks once, checked again, and removed if they still fail.
  8. Canary:   a question whose true answer isn't in the pages; the right answer is "not in the sources".

Every query, the chunk ids it retrieved (with scores), and every prompt and reply are logged (db.rag_log).
"""
import difflib
import hashlib
import io
import ipaddress
import json
import logging
import math
import os
import re
import secrets
import socket
import threading
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import numpy as np
import requests

import db
import pipeline

log = logging.getLogger("lifestory")

EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIMS = int(os.environ.get("EMBED_DIMS", "512"))
EMBED_PRICE = float(os.environ.get("PRICE_EMBED", "0.02"))        # $ per million tokens
LLM = os.environ.get("RAG_MODEL", "gpt-5-mini")
TOP_K = int(os.environ.get("RAG_TOP_K", "8"))
CHUNK_CHARS, CHUNK_MAX = 1000, 1500
PAGE_CHARS = 1800              # an estimated page, for documents that don't have their own pages (~300 words)
MAX_FILE = 40 * 1024 * 1024
MAX_CHUNKS = 30000
NOT_FOUND = "Not in the sources."

# The 20 questions. {person} is filled in at run time. The words after each are extra search words for the keyword
# half of the search (they never reach the model); they are about the kind of fact, never about one person.
QUERIES = [
    ("Where and when was {person} born?", "born birth birthplace birthday baptized native"),
    ("Where were {person}'s parents from, and what did they do?", "father mother parents trade occupation emigrated came from family"),
    ("What was {person}'s childhood like?", "boy girl boyhood girlhood childhood child young early years youth"),
    ("Who were {person}'s siblings?", "brother brothers sister sisters siblings youngest eldest children of his father"),
    ("What schooling or training did {person} have?", "school schooling education taught learned grammar apprentice training read books"),
    ("What was {person}'s first job?", "first job apprentice apprenticed work employed trade began working business"),
    ("An adventurous story from {person}'s life.", "adventure journey voyage escaped ran away travelled ship"),
    ("A scary or dangerous moment {person} faced.", "danger dangerous nearly drowned storm fire shipwreck narrowly escaped risk"),
    ("A funny anecdote about {person}.", "funny joke jest laughed laugh humor humour amusing anecdote wit"),
    ("A time {person} failed or made a serious mistake.", "mistake error erratum failed failure regret blunder wrong"),
    ("The hardest thing {person} went through.", "grief death loss illness sick hardship suffering sorrow lost"),
    ("Who did {person} marry, and what was that relationship like?", "married marry wife husband wedding courtship marriage"),
    ("What about {person}'s children?", "son sons daughter daughters children child born"),
    ("Who were {person}'s closest friends or mentors?", "friend friends friendship mentor companion club patron"),
    ("Who were {person}'s rivals or enemies?", "enemy enemies rival rivals opponent quarrel attacked hated dispute"),
    ("What is {person} best known for?", "famous known fame reputation celebrated renowned"),
    ("Something {person} made, invented or discovered.", "invented invention discovered discovery experiment made device"),
    ("Where did {person} travel or live?", "travelled traveled voyage lived moved residence abroad home settled"),
    ("A habit, hobby or quirk of {person}.", "habit habits hobby custom daily routine fond rule practice"),
    ("How did {person} die, and how is {person} remembered?", "died death funeral buried grave epitaph memory remembered legacy"),
]

STOP = set("""a an and are as at be been but by for from had has have he her hers him his i in into is it its me my
not of on or our she so than that the their them then there these they this those to was we were what when where which
who whom why will with you your did do does done how about after before over up out all any one""".split())


class Refused(ValueError):
    """Shown to the user as is."""


# ---------------------------------------------------------------------------
# Reading documents
# ---------------------------------------------------------------------------
def _decode(data):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _strip_gutenberg(text):
    """Keep only the book: drop Project Gutenberg's header and licence."""
    m = re.search(r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG[^\n]*\n", text, re.I)
    if m:
        text = text[m.end():]
    m = re.search(r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG", text, re.I)
    if m:
        text = text[:m.start()]
    return text


def _html_text(data):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(data, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        t.decompose()
    for t in soup.select('[role="navigation"], .navbox, .reflist, .mw-editsection, #toc, .toc, sup.reference'):
        t.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for t in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote", "pre"]):
        t.insert_before("\n\n")
    return soup.get_text()


def _epub_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    order = []
    try:                                                  # follow the book's reading order (the OPF spine)
        container = z.read("META-INF/container.xml").decode("utf-8", "replace")
        opf = re.search(r'full-path="([^"]+)"', container).group(1)
        o = z.read(opf).decode("utf-8", "replace")
        base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
        items = dict(re.findall(r'<item\b[^>]*?id="([^"]+)"[^>]*?href="([^"]+)"', o))
        items.update({i: h for h, i in re.findall(r'<item\b[^>]*?href="([^"]+)"[^>]*?id="([^"]+)"', o)})
        for idref in re.findall(r'<itemref\b[^>]*?idref="([^"]+)"', o):
            if idref in items:
                order.append(base + items[idref])
    except Exception:
        pass
    order = [n for n in order if n in names] or sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
    return "\n\n".join(_html_text(z.read(n)) for n in order)


def _docx_text(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    xml = z.read("word/document.xml").decode("utf-8", "replace")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
        paras.append(re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", t))))
    return "\n\n".join(paras)


def _kind(name, content_type, data):
    n, ct = (name or "").lower(), (content_type or "").lower()
    if n.endswith(".pdf") or "pdf" in ct or data[:5] == b"%PDF-":
        return "pdf"
    if n.endswith(".epub") or "epub" in ct:
        return "epub"
    if n.endswith(".docx") or "officedocument.wordprocessing" in ct:
        return "docx"
    if n.endswith((".html", ".htm", ".xhtml")) or "html" in ct or data[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return "html"
    if data[:2] == b"PK":
        raise Refused(f"{name}: that's a zip file. Upload the PDF, HTML, EPUB, Word or text files themselves.")
    if b"\x00" in data[:4096]:
        raise Refused(f"{name}: that doesn't look like a document this app can read (PDF, HTML, EPUB, Word or text).")
    return "text"


def read_document(name, data, content_type=""):
    """-> (kind, [(page_number, text)], real_pages). Pages are the PDF's own; other documents get estimated pages."""
    kind = _kind(name, content_type, data)
    if kind == "pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        except Exception as e:
            raise Refused(f"{name}: couldn't read this PDF ({str(e)[:80]}).")
        if sum(len(t.strip()) for _, t in pages) < 200:
            raise Refused(f"{name}: this PDF has no text layer (it's scanned pictures of pages). "
                          "Upload a PDF with selectable text, or a text/HTML version.")
        return kind, pages, True
    if kind == "epub":
        text = _epub_text(data)
    elif kind == "docx":
        text = _docx_text(data)
    elif kind == "html":
        text = _html_text(data)
    else:
        text = _decode(data)
    text = _strip_gutenberg(text)
    return kind, _estimate_pages(text), False


def _estimate_pages(text):
    paras = [p for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")) if p.strip()]
    pages, cur, n = [], [], 0
    for p in paras:
        cur.append(p)
        n += len(p)
        if n >= PAGE_CHARS:
            pages.append("\n\n".join(cur))
            cur, n = [], 0
    if cur:
        pages.append("\n\n".join(cur))
    return [(i + 1, t) for i, t in enumerate(pages)]


# ---------------------------------------------------------------------------
# Fetching links (safely: only public http(s) addresses, size-capped)
# ---------------------------------------------------------------------------
def _public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise Refused(f"Couldn't find the website {host}.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise Refused(f"{host} isn't a public website.")


def _gutenberg_url(url):
    """A Gutenberg book page (gutenberg.org/ebooks/20203) -> its plain-text file."""
    m = re.match(r"https?://(www\.|m\.|dev\.)?gutenberg\.org/(ebooks|etext)/(\d+)/?$", url.strip())
    return f"https://www.gutenberg.org/ebooks/{m.group(3)}.txt.utf-8" if m else url


def fetch(url):
    """-> (name, bytes, content_type)"""
    url = _gutenberg_url(url.strip())
    for _ in range(6):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise Refused(f"{url[:80]} isn't a web link (it must start with http:// or https://).")
        _public_host(u.hostname)
        r = requests.get(url, timeout=40, stream=True, allow_redirects=False,
                         headers={"User-Agent": "BeanstalkBooks/1.0 (MCON 368 student project; reads public biographies)"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        if r.status_code != 200:
            raise Refused(f"{u.hostname} answered {r.status_code} for {url[:100]}.")
        data = b""
        for part in r.iter_content(256 * 1024):
            data += part
            if len(data) > MAX_FILE:
                raise Refused(f"{url[:80]} is bigger than {MAX_FILE // 2**20} MB.")
        name = u.path.rstrip("/").rsplit("/", 1)[-1] or u.hostname
        return name, data, r.headers.get("content-type", "")
    raise Refused(f"{url[:80]} redirects too many times.")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
_SENT = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[\"'“‘(\[]?[A-Z0-9])")


def _clean(text):
    text = text.replace("­", "")
    text = re.sub(r"(\w)-\n\s*(\w)", r"\1\2", text)          # words split across lines
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)               # line breaks inside a paragraph
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)                   # Gutenberg _italics_
    return text


def chunk_pages(pages):
    """[(page, text)] -> [(page, chunk_text)]: ~1,000 characters each, cut at sentence ends, one sentence of overlap."""
    sents = []                                                  # (page, sentence)
    for page, text in pages:
        for para in re.split(r"\n\s*\n+", _clean(text)):
            para = para.strip()
            if not para:
                continue
            parts = _SENT.split(para)
            for s in parts:
                s = s.strip()
                while len(s) > CHUNK_MAX:                     # a run-on "sentence" (tables, lists): hard cut
                    cut = s.rfind(" ", 0, CHUNK_CHARS)
                    cut = cut if cut > 0 else CHUNK_CHARS
                    sents.append((page, s[:cut]))
                    s = s[cut:].strip()
                if s:
                    sents.append((page, s))
            if sents:
                sents.append((page, "\n"))                     # paragraph break marker
    out, cur, size = [], [], 0

    def flush():
        body = " ".join(s for _, s in cur if s != "\n").strip()
        body = re.sub(r"\s+", " ", body)
        if len(re.findall(r"[^\W\d_]", body)) >= 60:            # skip page furniture (numbers, stray headings)
            out.append((cur[0][0], body))

    for page, s in sents:
        if s == "\n":
            if size >= CHUNK_CHARS * 0.7:                       # a paragraph end near the target: a good place to cut
                flush()
                cur, size = [], 0
            continue
        if size + len(s) > CHUNK_CHARS and cur:
            flush()
            last = cur[-1] if cur[-1][1] != "\n" else None
            cur, size = ([last], len(last[1])) if last and len(last[1]) < 300 else ([], 0)
        cur.append((page, s))
        size += len(s) + 1
    if cur and size:
        flush()
    return out


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def _words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]


def _fake_embed(text):
    """For local testing without an API key: hashed bag of words. Same interface, much worse search."""
    v = np.zeros(EMBED_DIMS, dtype=np.float32)
    for w in _words(text):
        h = int(hashlib.md5(w.encode()).hexdigest()[:8], 16)
        v[h % EMBED_DIMS] += 1.0 if h & 1 else -1.0
    return v


def embed(texts, user_id=None):
    """-> float32 array (len(texts), EMBED_DIMS), each row unit length."""
    out = []
    for i in range(0, len(texts), 128):
        batch = [t[:6000] for t in texts[i:i + 128]]
        if pipeline.FAKE:
            vecs = [_fake_embed(t) for t in batch]
        else:
            t0 = time.time()
            for attempt in range(4):
                try:
                    r = pipeline.client().embeddings.create(model=EMBED_MODEL, input=batch, dimensions=EMBED_DIMS)
                    break
                except Exception as e:
                    if attempt == 3:
                        raise
                    log.warning("embed retry: %s", str(e)[:160])
                    time.sleep(2 * (attempt + 1))
            vecs = [np.array(d.embedding, dtype=np.float32) for d in r.data]
            tok = r.usage.total_tokens
            db.log_call(user_id=user_id, book_id=None, purpose="embed", model=EMBED_MODEL,
                        ms=int((time.time() - t0) * 1000), ok=1, input_tokens=tok, output_tokens=0,
                        cost_usd=tok * EMBED_PRICE / 1e6, detail=f"{len(batch)} chunks")
        out.extend(vecs)
    m = np.vstack(out).astype(np.float32) if out else np.zeros((0, EMBED_DIMS), np.float32)
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1
    return m / n


# ---------------------------------------------------------------------------
# Adding pages to a collection (runs in a background thread)
# ---------------------------------------------------------------------------
_corpus_locks = {}
_locks_lock = threading.Lock()


def _lock(corpus_id):
    with _locks_lock:
        return _corpus_locks.setdefault(corpus_id, threading.Lock())


def add_sources(corpus_id, user_id, files, urls):
    """files: [(name, bytes, content_type)]; urls: [str]. Each becomes one document row right away (so the page can
    show it), then they are read, chunked and embedded one after another in the background."""
    items = []
    for name, data, ct in files:
        items.append((db.add_doc(corpus_id, name=name[:300], source="upload", status="reading", kind=""),
                      name, data, ct, None))
    for u in urls:
        items.append((db.add_doc(corpus_id, name=u[:300], source=u[:600], status="reading", kind=""), u, None, "", u))
    db.update_corpus(corpus_id, status="adding", stage=f"Reading {len(items)} document(s)…")
    threading.Thread(target=_add_worker, args=(corpus_id, user_id, items), daemon=True).start()


def _add_worker(corpus_id, user_id, items):
    with _lock(corpus_id):
        for i, (doc_id, name, data, ct, url) in enumerate(items, 1):
            label = f"{i} of {len(items)}: {name[:80]}"
            try:
                if url:
                    db.update_corpus(corpus_id, stage=f"Downloading {label}")
                    name, data, ct = fetch(url)
                db.update_corpus(corpus_id, stage=f"Reading {label}")
                kind, pages, real = read_document(name, data, ct)
                data = None
                pieces = chunk_pages(pages)
                if not pieces:
                    raise Refused("no readable text found in it.")
                have = db.get_corpus(corpus_id)["chunks"]
                if have + len(pieces) > MAX_CHUNKS:
                    raise Refused(f"the collection would pass {MAX_CHUNKS:,} chunks (about "
                                  f"{MAX_CHUNKS * CHUNK_CHARS // PAGE_CHARS:,} pages). Start a new collection.")
                rows = []
                for j in range(0, len(pieces), 256):
                    db.update_corpus(corpus_id, stage=f"Embedding {label} — {min(j + 256, len(pieces))} of "
                                                      f"{len(pieces)} chunks")
                    part = pieces[j:j + 256]
                    vecs = embed([t for _, t in part], user_id)
                    rows += [(j + k, p, t, vecs[k].tobytes()) for k, (p, t) in enumerate(part)]
                db.add_chunks(corpus_id, doc_id, rows)
                chars = sum(len(t) for _, t in pages)
                db.update_doc(doc_id, kind=kind, chars=chars, pages=len(pages), real_pages=1 if real else 0,
                              chunks=len(rows), status="done", error=None, name=(url or name)[:300])
            except Refused as e:
                db.update_doc(doc_id, status="failed", error=str(e)[:400])
            except Exception as e:
                log.exception("adding %s failed", name)
                db.update_doc(doc_id, status="failed", error=f"Couldn't add it: {str(e)[:300]}")
        _index.pop(corpus_id, None)
        c = db.get_corpus(corpus_id)
        ok = [d for d in c["docs"] if d["status"] == "done"]
        db.update_corpus(corpus_id, status="ready" if ok else "empty",
                         stage=f"{len(ok)} document(s), about {sum(d['pages'] for d in ok):,} pages, "
                               f"{c['chunks']:,} chunks.")


# ---------------------------------------------------------------------------
# The search index: embeddings + BM25, kept in memory per collection, rebuilt from the database when it changes
# ---------------------------------------------------------------------------
_index = {}
_index_lock = threading.Lock()


class Index:
    def __init__(self, rows):
        self.ids = np.array([r.id for r in rows], dtype=np.int64)
        self.M = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows]) if rows else \
            np.zeros((0, EMBED_DIMS), np.float32)
        post, df, lens = {}, Counter(), []
        for i, r in enumerate(rows):
            tf = Counter(_words(r.text))
            lens.append(sum(tf.values()))
            for w, n in tf.items():
                post.setdefault(w, ([], []))
                post[w][0].append(i)
                post[w][1].append(n)
        self.post = {w: (np.array(a, np.int32), np.array(b, np.float32)) for w, (a, b) in post.items()}
        self.lens = np.array(lens, dtype=np.float32)
        self.avg = float(self.lens.mean()) if len(lens) else 1.0
        self.n = len(rows)

    def bm25(self, words, k1=1.4, b=0.75):
        s = np.zeros(self.n, dtype=np.float32)
        for w in set(words):
            if w not in self.post:
                continue
            idx, tf = self.post[w]
            idf = math.log(1 + (self.n - len(idx) + 0.5) / (len(idx) + 0.5))
            s[idx] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lens[idx] / self.avg))
        return s


def get_index(corpus_id):
    with _index_lock:
        ix = _index.get(corpus_id)
        if ix is None:
            ix = _index[corpus_id] = Index(db.corpus_chunks(corpus_id))
        return ix


def retrieve(corpus_id, question, keywords, person, k=TOP_K, qvec=None):
    """Merge a meaning search and a word search (reciprocal rank fusion) -> [(chunk_id, info)]."""
    ix = get_index(corpus_id)
    if ix.n == 0:
        return []
    qv = qvec if qvec is not None else embed([question])[0]
    cos = ix.M @ qv
    name_words = set(_words(person))                     # the name is in nearly every chunk: it doesn't help rank
    bm = ix.bm25([w for w in _words(question + " " + keywords) if w not in name_words])
    depth = min(ix.n, 40)
    by_cos = np.argsort(-cos)[:depth]
    by_bm = np.argsort(-bm)[:depth]
    fused = {}
    for rank, i in enumerate(by_cos):
        fused[int(i)] = fused.get(int(i), 0) + 1 / (60 + rank)
    for rank, i in enumerate(by_bm):
        if bm[i] > 0:
            fused[int(i)] = fused.get(int(i), 0) + 1 / (60 + rank)
    top = sorted(fused, key=lambda i: -fused[i])[:k]
    rc = {int(i): r for r, i in enumerate(by_cos)}
    rb = {int(i): r for r, i in enumerate(by_bm)}
    return [(int(ix.ids[i]), {"cos": round(float(cos[i]), 3), "bm25": round(float(bm[i]), 2),
                              "cos_rank": rc.get(i), "bm25_rank": rb.get(i)}) for i in top]


# ---------------------------------------------------------------------------
# The model calls (every prompt and reply goes to the log)
# ---------------------------------------------------------------------------
def _llm(story_id, step, system, user, qn=None, query=None, chunk_ids=None, effort="low"):
    t0 = time.time()
    if pipeline.FAKE:
        out = _fake_llm(step, user)
        tin = tout = 0
    else:
        last = None
        for attempt in range(3):
            try:
                r = pipeline.client().chat.completions.create(
                    model=LLM, response_format={"type": "json_object"}, reasoning_effort=effort,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                out = r.choices[0].message.content
                json.loads(out)
                break
            except Exception as e:
                last = e
                log.warning("%s call failed (%s), retrying", step, str(e)[:160])
                time.sleep(2 * (attempt + 1))
        else:
            db.log_rag(story_id, step=step, qn=qn, query=query, chunk_ids=json.dumps(chunk_ids or []),
                       prompt=f"SYSTEM:\n{system}\n\nUSER:\n{user}", response=f"ERROR: {last}", model=LLM,
                       ms=int((time.time() - t0) * 1000), input_tokens=0, output_tokens=0)
            raise RuntimeError(f"The model call for {step} failed: {str(last)[:200]}")
        tin, tout = r.usage.prompt_tokens, r.usage.completion_tokens
        db.log_call(user_id=None, book_id=None, purpose=f"rag_{step}"[:20], model=LLM,
                    ms=int((time.time() - t0) * 1000), ok=1, input_tokens=tin, output_tokens=tout,
                    cost_usd=(tin * pipeline.PRICE["llm_in"] + tout * pipeline.PRICE["llm_out"]) / 1e6,
                    detail=f"story {story_id} q{qn or ''}")
    db.log_rag(story_id, step=step, qn=qn, query=query, chunk_ids=json.dumps(chunk_ids or []),
               prompt=f"SYSTEM:\n{system}\n\nUSER:\n{user}", response=out, model=LLM if not pipeline.FAKE else "fake",
               ms=int((time.time() - t0) * 1000), input_tokens=tin, output_tokens=tout)
    return json.loads(out)


def _fake_llm(step, user):
    """Local testing only: pick a sentence from the first snippet so the whole flow can run without an API key."""
    if step in ("answer", "canary"):
        m = re.search(r"\[(c\d+)\][^\n]*\n(.+)", user)
        if not m or step == "canary":
            return json.dumps({"found": False, "facts": [], "answer": NOT_FOUND, "missing": "everything"})
        quote = " ".join(m.group(2).split()[:12])
        return json.dumps({"found": True, "facts": [{"fact": quote, "chunk": m.group(1), "quote": quote}],
                           "answer": quote, "missing": ""})
    if step == "story":
        facts = re.findall(r"^(f\d+) \(q(\d+), c\d+\): (.+)$", user, re.M)
        paras = {}
        for fid, q, text in facts:
            paras.setdefault(int(q), []).append({"text": text.rstrip(".") + ".", "facts": [fid]})
        return json.dumps({"title": "A life story", "paragraphs": [{"q": q, "sentences": s} for q, s in paras.items()]})
    if step in ("verify", "reverify"):
        ids = re.findall(r"^(s\d+):", user, re.M)
        return json.dumps({"sentences": [{"id": i, "supported": "yes", "unsupported": ""} for i in ids]})
    if step == "repair":
        ids = re.findall(r"^(s\d+):", user, re.M)
        return json.dumps({"sentences": [{"id": i, "text": ""} for i in ids]})
    return "{}"


def _snippets(chunks_by_id, ids):
    return "\n\n".join(f"[c{i}] ({chunks_by_id[i]['doc']}, page {chunks_by_id[i]['page']})\n{chunks_by_id[i]['text']}"
                       for i in ids if i in chunks_by_id)


ANSWER_SYSTEM = """You answer one question about {person}, using ONLY the snippets the user gives you. The snippets were
retrieved from documents the user uploaded; each starts with its chunk id in square brackets, like [c123].

Rules:
- Use only what the snippets say. Do not add anything from your own knowledge: no dates, places, names, numbers,
  explanations or background that the snippets don't state, even if you are sure it is true.
- Only use what is about {person}. Snippets can be about other people (relatives, people with the same surname).
- If the snippets don't answer the question, set found to false, facts to [], and answer to "Not in the sources."
  If they answer part of it, answer that part and say in "missing" what they don't say.
- For every fact give the chunk id it comes from and a quote: words copied exactly, letter for letter, from that
  chunk (5 to 30 words) that show the fact is true. One fact per chunk; split a fact that needs two chunks.
- Facts are short plain sentences about {person}, in your own words, and must not go beyond the quote's chunk.

Reply with only JSON:
{{"found": true/false,
  "facts": [{{"fact": "...", "chunk": "c123", "quote": "exact words from c123"}}],
  "answer": "2-4 plain sentences answering the question from the facts, or Not in the sources.",
  "missing": "what part of the question the snippets don't answer, or empty"}}"""

STORY_SYSTEM = """You write a true life story of {person} for children aged 6 to 9, to be read aloud from a picture
book. You may use ONLY the numbered facts the user gives you. They were taken from the user's documents and checked.

Rules:
- Every sentence must be built from one or more of the facts and must list the fact ids it uses.
- Add nothing that isn't in the facts: no names, dates, places, numbers, feelings, reasons, descriptions or events
  that the facts don't state, even if you know them. Simple words like "then", "later", "one day" are fine, and so
  is saying the same thing more simply ("his father" for "his parent", "very young" for "a child").
- Do not write sentences without a fact (no openings like "Let me tell you a story", no morals, no endings of your
  own). The title must also come from the facts (for example "The Life of NAME").
- Go in the order of the questions, which roughly follows a life. One paragraph per question that has facts; skip
  questions without facts. Use short, warm, clear sentences a child can follow. Don't mention sources or facts.

Reply with only JSON:
{{"title": "...", "paragraphs": [{{"q": 1, "sentences": [{{"text": "...", "facts": ["f1", "f2"]}}]}}]}}"""

VERIFY_SYSTEM = """You check a children's life story of {person} against its sources. For each sentence you get the
text of the chunks it cites. Decide whether everything the sentence says is stated in, or directly follows from,
those chunks.

- "yes": every claim is in the chunks. Simpler wording for children is fine ("dad" for "father", "very poor" for
  "in poverty"), and so are linking words ("then", "later", "one day").
- "partly": the main claim is there but a detail is not: a name, date, place, number, reason, feeling, description
  or event that the chunks don't give.
- "no": the main claim is not in the chunks.
Anything not in the chunks most likely came from the writer's own knowledge, so list exactly those words in
"unsupported". Be strict: a detail that is true in real life but missing from these chunks is still unsupported.

Reply with only JSON: {{"sentences": [{{"id": "s1", "supported": "yes|partly|no", "unsupported": "..."}}]}}"""

REPAIR_SYSTEM = """Some sentences in a children's life story of {person} say things their source chunks don't. Rewrite
each one so it says only what its chunks say, in the same simple style for children aged 6 to 9. Remove the
unsupported part; don't replace it with anything new. If nothing true is left to say, return an empty text.

Reply with only JSON: {{"sentences": [{{"id": "s1", "text": "..."}}]}}"""


# ---------------------------------------------------------------------------
# Checking quotes word for word
# ---------------------------------------------------------------------------
def _norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("—", "-") \
        .replace("–", "-")
    return " ".join(re.findall(r"[a-z0-9']+", s))


def quote_in_chunk(quote, text):
    q, t = _norm(quote), _norm(text)
    if not q:
        return False
    if q in t:
        return True
    m = difflib.SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
    return m.size >= 0.8 * len(q)


# ---------------------------------------------------------------------------
# Writing a story (runs in a background thread)
# ---------------------------------------------------------------------------
def start_story(corpus_id, user_id, canary):
    c = db.get_corpus(corpus_id)
    if not c or not c["chunks"]:
        raise Refused("Add some pages about the person first.")
    if c["status"] == "adding":
        raise Refused("Pages are still being added. Wait until they're done.")
    slug = secrets.token_urlsafe(9)
    sid = db.create_life_story(corpus_id=corpus_id, user_id=user_id, slug=slug, person=c["person"],
                               canary=(canary or "").strip()[:300] or None, status="running",
                               stage="Starting", progress=0, started_at=time.time())
    threading.Thread(target=_story_worker, args=(sid, corpus_id, c["person"], (canary or "").strip()[:300]),
                     daemon=True).start()
    return sid, slug


def _stage(sid, text, progress):
    db.update_life_story(sid, stage=text, progress=progress)


def _answer(sid, corpus_id, person, qn, question, keywords, qvec, step="answer"):
    hits = retrieve(corpus_id, question, keywords, person, qvec=qvec)
    ids = [i for i, _ in hits]
    db.log_rag(sid, step="retrieve", qn=qn, query=question, chunk_ids=json.dumps(ids),
               scores=json.dumps({f"c{i}": s for i, s in hits}), prompt=None, response=None, model=EMBED_MODEL,
               ms=0, input_tokens=0, output_tokens=0)
    chunks = db.get_chunks(ids)
    user = f"Question: {question}\n\nSnippets:\n\n{_snippets(chunks, ids)}"
    a = _llm(sid, step, ANSWER_SYSTEM.format(person=person), user, qn=qn, query=question, chunk_ids=ids)
    facts, dropped = [], []
    for f in a.get("facts") or []:
        cid = str(f.get("chunk", "")).strip().lstrip("[").rstrip("]").lower().lstrip("c")
        cid = int(cid) if cid.isdigit() else None
        reason = None
        if cid not in chunks:
            reason = "cites a chunk that wasn't retrieved for this question"
        elif not quote_in_chunk(f.get("quote", ""), chunks[cid]["text"]):
            reason = "its quote isn't in the chunk it cites"
        item = {"fact": str(f.get("fact", ""))[:600], "chunk": cid, "quote": str(f.get("quote", ""))[:600]}
        (dropped if reason else facts).append(dict(item, reason=reason) if reason else item)
    found = bool(facts)
    return {"q": qn, "question": question, "retrieved": ids, "scores": {f"c{i}": s for i, s in hits},
            "found": found, "facts": facts, "dropped": dropped,
            "answer": (a.get("answer") or "").strip() if found else NOT_FOUND,
            "missing": (a.get("missing") or "").strip() if found else "",
            "model_said_found": bool(a.get("found"))}


def _story_worker(sid, corpus_id, person, canary):
    try:
        questions = [(n + 1, q.format(person=person), kw) for n, (q, kw) in enumerate(QUERIES)]
        canary_q = canary.replace("{person}", person) if canary else ""
        _stage(sid, "Searching the pages for each of the 20 questions", 5)
        texts = [q for _, q, _ in questions] + ([canary_q] if canary_q else [])
        qvecs = embed(texts)
        answers, done = {}, [0]
        lock = threading.Lock()

        def one(n, q, kw, vec, step="answer"):
            r = _answer(sid, corpus_id, person, n, q, kw, vec, step)
            with lock:
                done[0] += 1
                _stage(sid, f"Answering the questions from the pages: {done[0]} of {len(texts)}",
                       5 + int(50 * done[0] / len(texts)))
            return r

        with ThreadPoolExecutor(6) as pool:
            futs = {n: pool.submit(one, n, q, kw, qvecs[n - 1]) for n, q, kw in questions}
            cfut = pool.submit(one, 21, canary_q, "", qvecs[-1], "canary") if canary_q else None
            for n, f in futs.items():
                answers[n] = f.result()
            canary_res = cfut.result() if cfut else None

        # --- the story, from checked facts only
        _stage(sid, "Writing the story from the facts", 60)
        facts, fid = {}, 0
        lines = []
        for n in sorted(answers):
            for f in answers[n]["facts"]:
                fid += 1
                key = f"f{fid}"
                facts[key] = dict(f, q=n)
                lines.append(f"{key} (q{n}, c{f['chunk']}): {f['fact']}")
        if not facts:
            raise Refused(f"None of the 20 questions could be answered from these pages. Are they about {person}?")
        qlist = "\n".join(f"q{n}: {answers[n]['question']}" + ("" if answers[n]["found"] else "  (no facts)")
                          for n in sorted(answers))
        user = f"Person: {person}\n\nQuestions, in order:\n{qlist}\n\nFacts:\n" + "\n".join(lines)
        s = _llm(sid, "story", STORY_SYSTEM.format(person=person), user, effort="medium")
        title = str(s.get("title") or f"The Life of {person}")[:160]
        sentences = []
        for p in s.get("paragraphs") or []:
            for st in p.get("sentences") or []:
                fids = [x for x in (st.get("facts") or []) if x in facts]
                chunk_ids = sorted({facts[x]["chunk"] for x in fids})
                sentences.append({"id": f"s{len(sentences) + 1}", "q": p.get("q"), "text": str(st.get("text", "")).strip(),
                                  "facts": fids, "chunks": chunk_ids})

        # --- check every sentence against the chunks it cites
        _stage(sid, f"Checking all {len(sentences)} sentences against the chunks they cite", 75)
        verdicts = _verify(sid, person, sentences, "verify")
        flagged = [x for x in sentences if verdicts.get(x["id"], {}).get("supported") != "yes"]
        for x in sentences:
            x["check"] = verdicts.get(x["id"], {"supported": "no", "unsupported": "the checker gave no verdict"})
        repaired, removed = [], []
        if flagged:
            _stage(sid, f"Rewriting {len(flagged)} sentence(s) that went beyond their chunks", 88)
            fixed = _repair(sid, person, flagged)
            retry = []
            for x in flagged:
                new = fixed.get(x["id"], "").strip()
                x["original"] = x["text"]
                if new and x["chunks"]:
                    x["text"] = new
                    retry.append(x)
                else:
                    x["removed"] = True
            if retry:
                again = _verify(sid, person, retry, "reverify")
                for x in retry:
                    v = again.get(x["id"], {"supported": "no"})
                    x["recheck"] = v
                    if v.get("supported") == "yes":
                        repaired.append(x["id"])
                    else:
                        x["removed"] = True
            removed = [x["id"] for x in flagged if x.get("removed")]

        kept = [x for x in sentences if not x.get("removed")]
        chunk_ids = sorted({c for x in sentences for c in x["chunks"]} |
                           {c for a in answers.values() for c in a["retrieved"]} |
                           set(canary_res["retrieved"] if canary_res else []))
        result = {
            "title": title, "person": person,
            "sentences": sentences,
            "answers": [answers[n] for n in sorted(answers)],
            "canary": canary_res and dict(canary_res, passed=not canary_res["found"]),
            "chunks": {f"c{k}": v for k, v in db.get_chunks(chunk_ids).items()},
            "review": {
                "sentences": len(sentences),
                "kept": len(kept),
                "cited": sum(1 for x in kept if x["chunks"]),
                "first_pass_supported": len(sentences) - len(flagged),
                "flagged": [x["id"] for x in flagged],
                "repaired": repaired,
                "removed": removed,
                "not_in_sources": [answers[n]["q"] for n in sorted(answers) if not answers[n]["found"]],
                "dropped_facts": sum(len(a["dropped"]) for a in answers.values()),
            },
        }
        db.update_life_story(sid, status="done", stage="Done", progress=100, result=json.dumps(result),
                             done_at=time.time())
    except Refused as e:
        db.update_life_story(sid, status="failed", stage="Failed", error=str(e), done_at=time.time())
    except Exception as e:
        log.exception("life story %s failed", sid)
        db.update_life_story(sid, status="failed", stage="Failed", error=f"Something went wrong: {str(e)[:300]}",
                             done_at=time.time())


def _groups(sentences, size=8):
    for i in range(0, len(sentences), size):
        yield sentences[i:i + size]


def _verify(sid, person, sentences, step):
    def run(group):
        ids = sorted({c for x in group for c in x["chunks"]})
        chunks = db.get_chunks(ids)
        body = "\n\n".join(f"{x['id']}: {x['text']}\nCites: {', '.join(f'c{c}' for c in x['chunks']) or 'nothing'}"
                           for x in group)
        user = f"Sentences:\n\n{body}\n\nChunks:\n\n{_snippets(chunks, ids)}"
        r = _llm(sid, step, VERIFY_SYSTEM.format(person=person), user, chunk_ids=ids)
        out = {}
        for v in r.get("sentences") or []:
            s = str(v.get("supported", "no")).lower()
            out[str(v.get("id"))] = {"supported": s if s in ("yes", "partly", "no") else "no",
                                     "unsupported": str(v.get("unsupported") or "")[:400]}
        for x in group:
            if not x["chunks"]:
                out[x["id"]] = {"supported": "no", "unsupported": "the sentence cites no chunk"}
        return out

    out = {}
    with ThreadPoolExecutor(6) as pool:
        for part in pool.map(run, list(_groups(sentences))):
            out.update(part)
    return out


def _repair(sid, person, sentences):
    def run(group):
        ids = sorted({c for x in group for c in x["chunks"]})
        chunks = db.get_chunks(ids)
        body = "\n\n".join(f"{x['id']}: {x['text']}\nCites: {', '.join(f'c{c}' for c in x['chunks'])}\n"
                           f"Not in the chunks: {x['check'].get('unsupported') or 'the main claim'}" for x in group)
        user = f"Sentences:\n\n{body}\n\nChunks:\n\n{_snippets(chunks, ids)}"
        r = _llm(sid, "repair", REPAIR_SYSTEM.format(person=person), user, chunk_ids=ids)
        return {str(v.get("id")): str(v.get("text") or "") for v in r.get("sentences") or []}

    out = {}
    with ThreadPoolExecutor(4) as pool:
        for part in pool.map(run, list(_groups([x for x in sentences if x["chunks"]]))):
            out.update(part)
    return out


def grep(corpus_id, phrase, limit=30):
    """Chunks containing a phrase (case-insensitive): for checking a canary really isn't in the pages."""
    p = phrase.lower()
    return [{"id": r.id, "page": r.page, "text": r.text}
            for r in db.corpus_chunks(corpus_id, with_embeddings=False) if p in r.text.lower()][:limit]


def paragraphs(r, include_removed=False):
    """The story's sentences grouped into paragraphs by question."""
    out, cur, q = [], [], object()
    for x in r["sentences"]:
        if x.get("removed") and not include_removed:
            continue
        if x["q"] != q and cur:
            out.append(cur)
            cur = []
        q = x["q"]
        cur.append(x)
    if cur:
        out.append(cur)
    return out


def story_markdown(r, s):
    cite = lambda x: " ".join(f"[c{c}]" for c in x["chunks"])
    lines = [f"# {r['title']}", "",
             f"*Written by the app from {r['person']}'s pages only. Each sentence ends with the chunk ids it comes "
             f"from; the chunks are listed at the end.*", ""]
    for p in paragraphs(r):
        lines += [" ".join(f"{x['text']} {cite(x)}" for x in p), ""]
    rv = r["review"]
    lines += ["## Not in the sources", ""]
    for a in r["answers"]:
        if not a["found"]:
            lines.append(f"- Q{a['q']}. {a['question']} — **not in the sources**; the story skips it.")
        elif a.get("missing"):
            lines.append(f"- Q{a['q']}. {a['question']} — partly: {a['missing']}")
    lines += ["", "## The check", "",
              f"- Sentences written: {rv['sentences']}; supported by their chunks on the first check: "
              f"{rv['first_pass_supported']}.",
              f"- Flagged as going beyond their chunks (possible training data): {len(rv['flagged'])}"
              + (f" — rewritten from the chunks and passed: {len(rv['repaired'])}; removed: {len(rv['removed'])}."
                 if rv["flagged"] else "."),
              f"- Sentences in the story: {rv['kept']}, every one citing at least one chunk: {rv['cited']} of "
              f"{rv['kept']}.",
              f"- Facts thrown out before writing because their quote wasn't in the cited chunk: {rv['dropped_facts']}."]
    for x in r["sentences"]:
        if x["id"] in rv["flagged"]:
            lines.append(f"  - {x['id']}: \"{x.get('original', x['text'])}\" — {x['check'].get('supported')}: "
                         f"{x['check'].get('unsupported') or ''}"
                         + (f" → removed" if x.get("removed") else f" → rewritten: \"{x['text']}\""))
    if r.get("canary"):
        c = r["canary"]
        lines += ["", "## Canary", "", f"Question: {c['question']}", "",
                  f"App's answer: {c['answer']}", "",
                  "Result: " + ("**passed** — it said not in the sources." if c["passed"] else
                                "**failed** — it found an answer in the pages (check whether the fact really is in "
                                "them).")]
    lines += ["", "## Chunks cited", ""]
    for k, v in sorted(r["chunks"].items(), key=lambda kv: int(kv[0][1:])):
        lines += [f"**{k}** — {v['doc']}, page {v['page']}", "", "> " + v["text"].replace("\n", " "), ""]
    return "\n".join(lines)
