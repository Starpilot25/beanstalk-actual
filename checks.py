"""
What the child's grown-up types is printed on a real book: the name on the cover ("starring Sarah") and the About Me
details on the back. Check it before anything is made or charged.

Three layers, cheapest first:
  1. Rules: a name is 1-3 words of letters (any alphabet), hyphens, apostrophes or periods, 2-30 characters.
  2. OpenAI's moderation model (free) on everything typed: anything it flags is refused.
  3. A small language-model check (fractions of a cent) for what moderation lets through: a name that is really an
     insult or a mean nickname ("Stinky", "Dummy"), and About Me details that don't belong in a child's book
     (swearing, insults, sexual content, or private details like a home address or phone number).
If the model checks can't run (an outage), the book is refused with "try again" rather than printed unchecked.
"""
import json
import logging
import re
import time

import db
import pipeline

log = logging.getLogger("checks")

NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-.][^\W\d_]+)*\.?$")
CHECK_MODEL = "gpt-5-mini"

PROMPT = """A grown-up is ordering a personalised children's picture book. The child's name is printed on the front
cover ("starring NAME") and the details are printed on the back cover. Judge what they typed.

name_ok: true only if the name reads as a real first name, or a normal nickname or diminutive a child could go by,
from any language or culture (Sarah, Xiaoming, Nkechi, Bobby, Mary-Kate, JJ, Ana Lucia are all fine). false if it is
an insult, epithet, slur, swear word, something sexual or rude, a mean or joke nickname (Stinky, Fatty, Dummy, Poopy),
a brand or product, a notorious real person, or not a name at all (a sentence, random letters, a number).

details_ok: true unless the age, likes or about text contains anything that should not be printed in a child's book:
swearing, insults or mocking the child, sexual content, violence or hate, or private details that identify where the
child is (a street address, phone number, email, school name). Ordinary facts about a child are fine.

Reply with only JSON: {"name_ok": bool, "name_reason": "short reason if false", "details_ok": bool,
"details_reason": "short reason if false"}"""


class Refused(ValueError):
    """The message is shown to the user as is."""


# The page checks the details as soon as they're typed (POST /api/check-details), so by the time the photo is
# uploaded the answer is cached and the book's 60-second clock doesn't pay for it.
_cache = {}
CACHE_SECONDS = 1800


def _rules(name):
    if not name:
        raise Refused("Type the child's first name: it goes on the cover.")
    if len(name) < 2 or len(name) > 30 or len(name.split()) > 3:
        raise Refused("Use the child's first name (or first and middle name): 2 to 30 letters.")
    if not NAME_RE.match(name):
        raise Refused("A name can only have letters, spaces, hyphens and apostrophes.")
    if re.search(r"(.)\1\1\1", name.lower()):
        raise Refused("That doesn't look like a real name. Type the child's first name.")


def check_details(details, user_id=None):
    """Raise Refused with a friendly message if the name or About Me details shouldn't be printed."""
    key = json.dumps([details.get(k, "") for k in ("child_name", "age", "likes", "about")])
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        if hit[1]:
            raise Refused(hit[1])
        return
    try:
        _check(details, user_id)
    except Refused as e:
        if "try again" not in str(e):        # don't cache an outage
            _cache[key] = (time.time(), str(e))
        raise
    _cache[key] = (time.time(), None)


def _check(details, user_id):
    name = details.get("child_name", "").strip()
    _rules(name)
    if pipeline.FAKE:                        # local testing: rules only
        return
    text = "\n".join(f"{k}: {details.get(k, '')}" for k in ("child_name", "age", "likes", "about"))
    t0 = time.time()
    try:
        m = pipeline.client().moderations.create(model="omni-moderation-latest", input=text)
        flagged = m.results[0].flagged
        db.log_call(user_id=user_id, book_id=None, purpose="check_text", model="omni-moderation-latest",
                    ms=int((time.time() - t0) * 1000), ok=1, input_tokens=0, output_tokens=0, cost_usd=0.0,
                    detail=f"flagged={flagged}")
        if flagged:
            raise Refused("Something in the name or About Me details can't be printed in a children's book. "
                          "Please change it.")
        t1 = time.time()
        r = pipeline.client().chat.completions.create(
            model=CHECK_MODEL, response_format={"type": "json_object"}, reasoning_effort="minimal",
            messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": text}])
        a = json.loads(r.choices[0].message.content)
        tin, tout = r.usage.prompt_tokens, r.usage.completion_tokens
        db.log_call(user_id=user_id, book_id=None, purpose="check_text", model=CHECK_MODEL,
                    ms=int((time.time() - t1) * 1000), ok=1, input_tokens=tin, output_tokens=tout,
                    cost_usd=(tin * pipeline.PRICE["llm_in"] + tout * pipeline.PRICE["llm_out"]) / 1e6,
                    detail=json.dumps(a)[:250])
    except Refused:
        raise
    except Exception as e:
        log.warning("text check failed: %s", e)
        raise Refused("We couldn't check the name and details just now. Please try again in a minute.")
    if not a.get("name_ok", False):
        raise Refused(f"“{name}” can't go on the cover"
                      + (f" ({a.get('name_reason')})" if a.get("name_reason") else "")
                      + ". Please type the child's real first name.")
    if not a.get("details_ok", False):
        raise Refused("Something in the About Me details can't be printed"
                      + (f": {a.get('details_reason')}" if a.get("details_reason") else "") + ". Please change it.")
