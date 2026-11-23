"""
Ten AI personas review the real 20-page book, the same four questions as the real testers (SURVEY.md).

How they differ (so they aren't ten copies of one answer). Each persona has
  - a different life: age 19 to 71, parents, a grandparent, a teacher, an illustrator, not a parent;
  - a different face, which is what really tests the app: glasses, a beard, a hijab, gray hair, freckles, curly
    hair, a shaved head, different skin tones;
  - a different story (five get Jack and the Beanstalk, five Little Red Riding Hood) and a different history with it
    (one didn't grow up with it);
  - a different bar (generous, harsh, impatient, expert) and a different way of writing.
And each one reviews their OWN book: a photo of them is made, the app's real pipeline makes their full book from
it (hero sheet, 15 painted pages, checks and repaints, the PDF), and then a vision model, playing that persona, sees
their photo and every page with its words and answers the survey.

The shared art (character bible and pre-made scenes) is downloaded once from the live site, so the books match
what real users get. Pictures are made at low quality to keep it cheap (see below). Run it on your computer from
the project folder (it uses your OpenAI key from .env; roughly $0.25 a persona, about $2-3 for all ten, and
15-20 minutes):
    py -m pip install -r requirements.txt
    py personas/run_personas.py          (all ten)
    py personas/run_personas.py p03 p07  (just some)
It skips any step whose file already exists, so a rerun after a failure doesn't pay twice.
Output: personas/out/<id>/ (photo.jpg, book.pdf, answers.json), personas/out/responses.csv and responses.md.
"""
import base64
import csv
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"
SITE = os.environ.get("PERSONA_SITE", "https://beanstalk.autosignusa.com")
sys.path.insert(0, str(ROOT))

# Read .env (KEY=VALUE lines) if there is one, without needing another package.
env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
OUT.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + str(OUT / "personas.db")   # never the live database
if os.environ.get("IMAGE_MODEL") == "fake":
    os.environ.pop("IMAGE_MODEL")            # a fake left over from testing would waste the run
# Keep the run cheap: low-quality pictures (about a quarter of the price of the site's "medium"; the faces and
# layout are still clear enough to judge), and no repaints of pages that are only imperfect (pages that are
# wrong, e.g. the hero missing, still get their retries). Set PERSONA_QUALITY=medium to match the live site.
os.environ["PAGE_QUALITY"] = os.environ.get("PERSONA_QUALITY", "low")
os.environ.setdefault("RETRY_DEADLINE", "0")

import db                                    # noqa: E402
import pipeline                              # noqa: E402  the app's real pipeline, prompts and checks
import stories as S                          # noqa: E402
from PIL import Image                        # noqa: E402

REVIEW_MODEL = os.environ.get("PERSONA_MODEL", "gpt-5-mini")

PERSONAS = [
    dict(id="p01", name="Denise", age=34, kids="Yes, under 10", device="Phone",
         look="a 34-year-old Black woman with short natural coily hair, round tortoiseshell glasses, warm brown skin",
         who="Pediatric nurse in Atlanta, two kids (4 and 7). Reads to them every night. Uses her phone for everything.",
         story="Knows the story well; reads the classic version to her kids.",
         judge="Generous, but she notices faces closely because her kids would. Glasses matter to her: she always wears them.",
         voice="Friendly, a few full sentences, the odd exclamation mark."),
    dict(id="p02", name="Hank", age=71, kids="Yes, 10 or older", device="Computer",
         look="a 71-year-old white man, bald on top with short white hair at the sides, a full white beard, deep smile lines",
         who="Retired machinist in Ohio, six grandchildren. Not comfortable with websites; his daughter set up his Gmail.",
         story="Grew up with the story; remembers 'Fee-fi-fo-fum' and the giant.",
         judge="Suspicious of computer pictures. Cares whether it looks like a real book he'd give his grandkids.",
         voice="Short, plain, a bit gruff. No exclamation marks."),
    dict(id="p03", name="Amira", age=28, kids="No", device="Phone",
         look="a 28-year-old Arab-American woman wearing a dusty-rose hijab, dark eyes, light olive skin, thick eyebrows",
         who="UX designer in Dearborn. Not a parent. Thinks about every app she uses like a design review.",
         story="Knows it from cartoons.",
         judge="Critical in a useful way: names specific problems with layout, wait times and wording. Checks whether the hijab was kept.",
         voice="Crisp, specific, bullet-like phrases, design vocabulary."),
    dict(id="p04", name="Kenji", age=41, kids="Yes, under 10", device="Computer",
         look="a 41-year-old Japanese man with black hair in a short undercut, thin rectangular black glasses, clean-shaven",
         who="Software engineer in Seattle, one daughter (5). Will poke at the site and notice how it's built.",
         story="Read it in English as an adult; knows the outline.",
         judge="Fair, numbers-minded. Impressed by the tech, picky about consistency between pages.",
         voice="Precise and dry, mentions small technical details."),
    dict(id="p05", name="Lupe", age=56, kids="Yes, 10 or older", device="Tablet",
         look="a 56-year-old Mexican woman with long gray-streaked black hair in a low bun, gold hoop earrings, laugh lines",
         who="Owns a bakery in San Antonio, three grown children, first grandchild on the way. English is her second language.",
         story="Did not grow up with this story; heard it once or twice.",
         judge="Warm, emotional, thinking of her grandchild. Would buy it as a gift if it felt special.",
         voice="Warm, simple English with small grammar slips, sometimes a Spanish word."),
    dict(id="p06", name="Tyler", age=19, kids="No", device="Phone",
         look="a 19-year-old white man with messy red hair, lots of freckles, a faint mustache, a hoodie",
         who="College sophomore in Arizona doing studies for money between classes. Wants to finish fast.",
         story="Vaguely remembers it.",
         judge="Impatient. Annoyed by waiting. Low effort but honest.",
         voice="all lowercase, very short, slang, no punctuation"),
    dict(id="p07", name="Grace", age=63, kids="Yes, 10 or older", device="Computer",
         look="a 63-year-old Korean-American woman with a short silver bob, small pearl earrings, rimless glasses",
         who="Retired second-grade teacher in New Jersey. Taught reading for 30 years.",
         story="Has taught the story many times and knows several versions.",
         judge="Judges the words as much as the pictures: reading level, rhythm, whether the text and picture agree.",
         voice="Careful, complete sentences, gently corrective, like a teacher's note."),
    dict(id="p08", name="Marcus", age=37, kids="Yes, under 10", device="Phone",
         look="a 37-year-old Black man with a shaved head, a neat short black beard, dark brown skin, a broad smile",
         who="Firefighter in Chicago, twin boys (6). Busy; would use this to surprise his kids.",
         story="Knows it from childhood.",
         judge="Easygoing. Mostly cares whether his boys would think it's him.",
         voice="Casual, upbeat, short sentences."),
    dict(id="p09", name="Priya", age=45, kids="Yes, under 10", device="Computer",
         look="a 45-year-old Indian woman with shoulder-length wavy black hair, a small nose stud, medium brown skin",
         who="Professional children's book illustrator in Boston, one son (8).",
         story="Knows it and many illustrated editions of it.",
         judge="Harsh on art direction: anatomy, hands, consistency, composition, typography. Hard to impress.",
         voice="Expert and blunt, uses illustration terms."),
    dict(id="p10", name="Sam", age=24, kids="No", device="Computer",
         look="a 24-year-old nonbinary Latinx person with chin-length curly dyed-teal hair, a septum ring, light brown skin",
         who="Grad student in Portland. Cares about privacy and about who gets represented in kids' books.",
         story="Knows it.",
         judge="Reads the privacy page. Notices whether the app handles a face that isn't a typical 'Jack'.",
         voice="Thoughtful, medium length, a bit wry."),
]

# Which book each persona makes, and the name they type in.
STORY = {"p01": "red", "p02": "jack", "p03": "red", "p04": "jack", "p05": "red",
         "p06": "jack", "p07": "red", "p08": "jack", "p09": "red", "p10": "jack"}

QUESTIONS = """Answer the survey about the book you just made. Use the 1-5 scales exactly as written.
1. Does this look like you? 1 (not at all) - 5 (anyone would recognize me)
2. Why that score? What's right or off about the face, on which pages?
3. Does the story ring true? Does it feel like the real fairy tale, and like a real children's book? 1-5
4. Why that score?
5. Does it look professional? Would you print it, gift it, or pay 99 cents for it? 1 (cheap AI demo) - 5 (real published book)
6. Why that score?
7. What isn't good? Anything that bugged you: name the page if you can.
8. Anything you liked? (optional, may be empty)
Reply with only a JSON object with keys: looks_like_me (int), looks_like_me_why, rings_true (int), rings_true_why,
professional (int), professional_why, not_good, liked."""


def fetch(path):
    with urllib.request.urlopen(SITE + path, timeout=60) as r:
        return r.read()


def thumb(raw, side=512):
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def seed(story):
    """Copy the live site's shared art for one story into the local database (once)."""
    for key, (name, desc) in S.BIBLE[story].items():
        if not db.get_bible(story, key):
            try:
                db.save_bible(story, key, name, desc, fetch(f"/bible/{story}/{key}.jpg"))
            except Exception as e:
                print(f"  bible {story}/{key} not downloaded ({e}); scenes will draw it from its description")
    for n in range(0, 21):
        if db.get_scene(story, n, thumb=True)[0] is None:
            raw = fetch(f"/scene/{story}/{n}.jpg?full=1")
            db.save_scene(story, n, raw, thumb(raw), 1, None, {})
    print(f"shared art for {story} ready")


def save_jpeg(raw, path, side=None):
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if side:
        im.thumbnail((side, side))
    im.save(path, "JPEG", quality=88)


def img_part(path):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + data, "detail": "high"}}


def make_book(p, d):
    """The persona's own book, made by the app's real pipeline. Returns the pages as files."""
    pdf = d / "book.pdf"
    story = STORY[p["id"]]
    if not pdf.exists():
        uid = db.upsert_user("persona-" + p["id"], f"{p['id']}@personas.local", p["name"], None)
        details = {"child_name": p["name"], "age": str(p["age"]), "likes": "", "about": ""}
        book_id = db.create_book(uid, story, details, time.time())
        t = time.time()
        pipeline.run_book(book_id, uid, pipeline.to_input((d / "photo.jpg").read_bytes()))
        b = db.get_book_internal(book_id)
        pdf.write_bytes(b["pdf"])
        for n, (raw, zone) in db.page_images_internal(book_id).items():
            save_jpeg(raw, d / f"page{n:02d}.jpg", 1024)
        (d / "book.json").write_text(json.dumps({"book_id": book_id, "story": story,
                                                 "seconds": round(time.time() - t, 1)}))
        print(p["id"], f"book done in {time.time() - t:.0f} s")
    return story


def run(p):
    d = OUT / p["id"]
    d.mkdir(exist_ok=True)
    photo = d / "photo.jpg"
    if not photo.exists():
        r = pipeline.client().images.generate(
            model=pipeline.IMAGE_MODEL, size="1024x1024", quality="low", n=1,
            prompt=(f"A natural, candid smartphone photo of {p['look']}, head and shoulders, facing the camera, "
                    "soft daylight by a window at home, sharp focus on the face, realistic skin, no filters."))
        save_jpeg(base64.b64decode(r.data[0].b64_json), photo)
        print(p["id"], "photo")
    story = make_book(p, d)

    ans_file = d / "answers.json"
    if ans_file.exists() and not ans_file.read_bytes().strip():
        ans_file.unlink()                    # an empty file left by a failed write: answer again
    if not ans_file.exists():
        title = S.STORIES[story]["title"] if "title" in S.STORIES[story] else story
        system = (f"You are {p['name']}, {p['age']}. {p['who']} Story: {p['story']} How you judge: {p['judge']} "
                  f"How you write: {p['voice']} You are taking a paid 3-minute survey about a personalised picture "
                  "book. Answer as yourself, from what you actually see in the images, not as an AI and not to please "
                  "anyone. Use the whole 1-5 range honestly; a 3 is fine and so is a 1 or a 5. Stay in your own voice.")
        content = [{"type": "text", "text": f"Image 1 is the photo of you that you uploaded. Then comes every page "
                    f"of the PDF the app made you: {title}, with you as the hero."}, img_part(photo)]
        pages = {pg["n"]: pg for pg in S.all_pages(story)}
        for f in sorted(d.glob("page*.jpg")):
            n = int(f.stem[4:])
            words = "This is the cover." if n == 0 else f"The book prints these words with it: \"{pages[n]['text']}\""
            content += [{"type": "text", "text": f"Page {n}. {words}"}, img_part(f)]
        content.append({"type": "text", "text": f"You used a {p['device'].lower()}.\n\n" + QUESTIONS})
        r = pipeline.client().chat.completions.create(
            model=REVIEW_MODEL, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}])
        a = json.loads(r.choices[0].message.content)
        # UTF-8 explicitly: Windows defaults to cp1252, which can't write characters like a non-breaking hyphen.
        ans_file.write_text(json.dumps(a, indent=2, ensure_ascii=False), encoding="utf-8")
        print(p["id"], "answers")
    return p, read_json(ans_file)


def read_json(f):
    """Answers saved by older runs on Windows are cp1252, newer ones UTF-8."""
    raw = f.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return json.loads(text) if text.strip() else None


def age_range(a):
    for lo, hi, s in [(18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54"), (55, 64, "55-64")]:
        if lo <= a <= hi:
            return s
    return "65+"


def main():
    want = set(sys.argv[1:])
    todo = [p for p in PERSONAS if not want or p["id"] in want]
    for story in sorted({STORY[p["id"]] for p in todo}):
        seed(story)
    failed = []
    for p in todo:                    # one book at a time: each book already paints 16 pictures in parallel
        try:
            run(p)
        except Exception as e:
            failed.append(p["id"])
            print(p["id"], "FAILED:", str(e)[:300])
    if failed:
        print("\nFailed:", " ".join(failed), "- run again with those ids; finished steps are skipped.")

    rows = []
    for p in PERSONAS:
        f = OUT / p["id"] / "answers.json"
        a = read_json(f) if f.exists() else None
        if a:
            rows.append((p, a))
    cols = ["id", "name", "story", "age_range", "children", "device", "looks_like_me", "looks_like_me_why",
            "rings_true", "rings_true_why", "professional", "professional_why", "not_good", "liked"]
    with open(OUT / "responses.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for p, a in rows:
            w.writerow([p["id"], p["name"], STORY[p["id"]], age_range(p["age"]), p["kids"], p["device"]]
                       + [a.get(c, "") for c in cols[6:]])
    md = ["# AI persona responses", "", f"Made by `personas/run_personas.py`: each persona's own 20-page book from the "
          f"app's real pipeline (image model `{pipeline.IMAGE_MODEL}`, `{pipeline.QUALITY}` quality to keep the run cheap), reviewed by `{REVIEW_MODEL}` playing that "
          "persona.", ""]
    for p, a in rows:
        i = p["id"]
        md += [f"## {p['name']}, {p['age']} ({'Jack' if STORY[i] == 'jack' else 'Red Riding Hood'}): {p['who']}", "",
               f"<img src='{i}/photo.jpg' width='140'> <img src='{i}/page00.jpg' width='220'> "
               f"<img src='{i}/page01.jpg' width='220'> <img src='{i}/page12.jpg' width='220'>", "",
               f"- **Looks like me:** {a.get('looks_like_me')}/5. {a.get('looks_like_me_why', '')}",
               f"- **Rings true:** {a.get('rings_true')}/5. {a.get('rings_true_why', '')}",
               f"- **Professional:** {a.get('professional')}/5. {a.get('professional_why', '')}",
               f"- **What isn't good:** {a.get('not_good', '')}",
               f"- **Liked:** {a.get('liked', '') or '-'}", ""]
    (OUT / "responses.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n{len(rows)} of {len(PERSONAS)} personas done. See personas/out/responses.md")


if __name__ == "__main__":
    main()
