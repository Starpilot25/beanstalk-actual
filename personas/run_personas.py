"""
Ten AI personas take the same survey as the real testers (see SURVEY.md).

Approach: the personas are spread on purpose so they don't all sound like one AI. They differ in
  - who they are: age 19 to 71, parents, a grandparent, a teacher, an illustrator, not a parent;
  - what their face looks like (this is what actually tests the app): glasses, a beard, a hijab, gray hair,
    freckles, curly hair, a shaved head, different skin tones;
  - how well they know the story (one didn't grow up with it);
  - how hard they are to please, and how they write (terse, chatty, lowercase, English as a second language).
Each persona really goes through the app: a photo of them is made, then the app's own prompts make their cast
sheet and the three pages, then a vision model, playing that persona, looks at their photo and their book and
answers the survey questions.

Run it on your computer from the project folder (it uses your own OpenAI key; ~5 pictures per persona,
about $2.50 for all ten):
    py -m pip install -r requirements.txt
    set OPENAI_API_KEY=sk-...            (PowerShell: $env:OPENAI_API_KEY="sk-...")  or put it in .env
    py personas/run_personas.py          (all ten)
    py personas/run_personas.py p03 p07  (just some)

It skips any step whose file already exists, so if one call fails you can run it again without paying twice.
Output: personas/out/<id>/ (photo, sheet, pages, answers.json), personas/out/responses.csv and responses.md.
"""
import base64
import csv
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"
sys.path.insert(0, str(ROOT))

# Read .env (KEY=VALUE lines) if there is one, without needing another package.
env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault("DATABASE_URL", "sqlite:///" + str(OUT / "personas.db"))
if os.environ.get("IMAGE_MODEL") == "fake" and not os.environ.get("PERSONA_DRY_RUN"):
    os.environ.pop("IMAGE_MODEL")            # a fake left over from testing would waste the run
OUT.mkdir(exist_ok=True)

import app as beanstalk                     # the app's own prompts and model settings  # noqa: E402
from storyboard import PAGES                # noqa: E402

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

QUESTIONS = """Answer the survey about the book you just made. Use the 1-5 scales exactly as written.
5. Does Jack look like you? 1 (not at all) - 5 (anyone would recognize me)
6. Why that score? What's right or off about the face?
7. Does the story ring true? Do the pages feel like Jack and the Beanstalk, and like a real children's book? 1-5
8. Why that score?
9. Does it look professional? Would you print it, gift it, or pay for it? 1 (looks like a cheap AI demo) - 5 (looks like a real published book)
10. Why that score?
11. What isn't good? Anything that bugged you.
12. Anything you liked? (optional, may be empty)
Reply with only a JSON object with keys: looks_like_me (int), looks_like_me_why, rings_true (int), rings_true_why,
professional (int), professional_why, not_good, liked."""


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def img_part(path):
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64(path), "detail": "high"}}


def save_jpeg(raw, path):
    from PIL import Image
    Image.open(io.BytesIO(raw)).convert("RGB").save(path, "JPEG", quality=90)


def edit(images, prompt, label):
    """One image call through the app itself, the same way the website makes it."""
    return beanstalk.generate(images, prompt, uid=None, book_id=None, action="persona", target=label, label=label)


def run(p):
    d = OUT / p["id"]
    d.mkdir(exist_ok=True)
    photo, sheet = d / "photo.jpg", d / "sheet.jpg"

    if not photo.exists() and beanstalk.FAKE:   # PERSONA_DRY_RUN=1 IMAGE_MODEL=fake: free test of the pipeline
        save_jpeg(beanstalk.fake_image("photo " + p["id"]), photo)
    if not photo.exists():
        r = beanstalk.client().images.generate(
            model=beanstalk.IMAGE_MODEL, size="1024x1024", quality="medium", n=1,
            prompt=(f"A natural, candid smartphone photo of {p['look']}, head and shoulders, facing the camera, "
                    "soft daylight by a window at home, sharp focus on the face, realistic skin, no filters."))
        save_jpeg(base64.b64decode(r.data[0].b64_json), photo)
        print(p["id"], "photo")

    if not sheet.exists():
        save_jpeg(edit(beanstalk.to_png(photo.read_bytes(), "photo.png"), beanstalk.hero_prompt(), "sheet"), sheet)
        print(p["id"], "sheet")

    def page(pg):
        f = d / f"page{pg['n']}.jpg"
        if not f.exists():
            save_jpeg(edit(beanstalk.to_png(sheet.read_bytes(), "sheet.png"), beanstalk.page_prompt(pg),
                           f"page{pg['n']}"), f)
            print(p["id"], "page", pg["n"])
    with ThreadPoolExecutor(3) as ex:            # pages in parallel, like "Paint all pages"
        list(ex.map(page, PAGES))

    ans_file = d / "answers.json"
    if not ans_file.exists():
        system = (f"You are {p['name']}, {p['age']}. {p['who']} Story: {p['story']} How you judge: {p['judge']} "
                  f"How you write: {p['voice']} You are taking a paid 10-minute survey. Answer as yourself, from what "
                  "you actually see in the images, not as an AI and not to please anyone. Use the whole 1-5 range "
                  "honestly; a 3 is fine and so is a 1 or a 5. Stay in your own voice in every text answer.")
        content = [{"type": "text", "text": "Image 1 is the photo of you that you uploaded. Image 2 is the cast sheet "
                    "the app made (you as Jack on the left; you, Jack's mother and the cow on the right)."},
                   img_part(photo), img_part(sheet)]
        for pg in PAGES:
            content += [{"type": "text", "text": f"Page {pg['n']}. The book prints these words over the picture: "
                         f"\"{pg['text']}\""}, img_part(d / f"page{pg['n']}.jpg")]
        content.append({"type": "text", "text": f"You used a {p['device'].lower()}. Sign-in and painting worked.\n\n"
                        + QUESTIONS})
        if beanstalk.FAKE:
            ans_file.write_text(json.dumps({"looks_like_me": 3, "looks_like_me_why": "dry run", "rings_true": 3,
                "rings_true_why": "dry run", "professional": 3, "professional_why": "dry run",
                "not_good": "dry run", "liked": ""}))
            return p, json.loads(ans_file.read_text())
        r = beanstalk.client().chat.completions.create(
            model=REVIEW_MODEL, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}])
        a = json.loads(r.choices[0].message.content)
        ans_file.write_text(json.dumps(a, indent=2, ensure_ascii=False))
        print(p["id"], "answers")
    return p, json.loads(ans_file.read_text())


def age_range(a):
    for lo, hi, s in [(18, 24, "18–24"), (25, 34, "25–34"), (35, 44, "35–44"), (45, 54, "45–54"), (55, 64, "55–64")]:
        if lo <= a <= hi:
            return s
    return "65+"


def main():
    want = set(sys.argv[1:])
    todo = [p for p in PERSONAS if not want or p["id"] in want]
    results, failed = [], []
    with ThreadPoolExecutor(3) as ex:
        for p, fut in [(p, ex.submit(run, p)) for p in todo]:
            try:
                results.append(fut.result())
            except Exception as e:
                failed.append(p["id"])
                print(p["id"], "FAILED:", str(e)[:300])
    if failed:
        print("\nFailed:", " ".join(failed), "- run again with those ids; finished steps are skipped.")
        print(f"(If the error is about the model '{REVIEW_MODEL}', set PERSONA_MODEL to another vision model.)")

    # Everything that has answers, in persona order (also picks up earlier runs).
    rows = []
    for p in PERSONAS:
        f = OUT / p["id"] / "answers.json"
        if f.exists():
            rows.append((p, json.loads(f.read_text())))
    cols = ["id", "name", "age_range", "children", "device", "looks_like_me", "looks_like_me_why", "rings_true",
            "rings_true_why", "professional", "professional_why", "not_good", "liked"]
    with open(OUT / "responses.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for p, a in rows:
            w.writerow([p["id"], p["name"], age_range(p["age"]), p["kids"], p["device"]] + [a.get(c, "") for c in cols[5:]])

    md = ["# AI persona responses", "", f"Made by `personas/run_personas.py` (image model `{beanstalk.IMAGE_MODEL}`, "
          f"reviewer `{REVIEW_MODEL}`). Each persona's photo, book and answers.", ""]
    for p, a in rows:
        i = p["id"]
        md += [f"## {p['name']}, {p['age']}: {p['who']}", "",
               f"<img src='{i}/photo.jpg' width='140'> <img src='{i}/sheet.jpg' width='300'> "
               f"<img src='{i}/page1.jpg' width='220'> <img src='{i}/page2.jpg' width='220'> <img src='{i}/page3.jpg' width='220'>", "",
               f"- **Looks like me:** {a.get('looks_like_me')}/5. {a.get('looks_like_me_why', '')}",
               f"- **Rings true:** {a.get('rings_true')}/5. {a.get('rings_true_why', '')}",
               f"- **Professional:** {a.get('professional')}/5. {a.get('professional_why', '')}",
               f"- **What isn't good:** {a.get('not_good', '')}",
               f"- **Liked:** {a.get('liked', '') or '—'}", ""]
    (OUT / "responses.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n{len(rows)} of {len(PERSONAS)} personas done. See personas/out/responses.md and responses.csv")


if __name__ == "__main__":
    main()
