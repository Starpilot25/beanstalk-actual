"""
The books, as data: one 20-page TEMPLATE shared by both stories, the two STORIES, and the character BIBLE.

How a page is made
  1. Once, ahead of time (admin page): each supporting character in the BIBLE is drawn on a plain background,
     then every scene is drawn with those characters as reference images, leaving an empty spot where the
     hero will stand. Bible images and scenes are stored in the database and shared by every book.
  2. Per book: the child's photo becomes a hero sheet (face close-up + full body, in the story's costume).
  3. Per book: the hero sheet is edited into each pre-made scene that has a hero slot, all in parallel.
     Every result is analysed; failures are repainted, at most 3 attempts, and the best one is kept.
  4. The PDF lays every page out by the TEMPLATE and puts the words in a band the analysis found clear.

The TEMPLATE is what holds quality steady across the two stories: page k of either story has the same
layout, the same shot, the same hero position and the same allowed places for text.
"""

# House style: word for word in every image call.
STYLE = "Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light."
NO_WORDS = "Pure illustration with no lettering anywhere."
HANDS = ("Every hand is anatomically correct: one thumb and four fingers, natural proportions, "
         "fingers clearly separated.")

# ---------------------------------------------------------------------------------------------------------
# The template: 20 page slots. Both stories fill the same slots.
#   layout  "full"   = art fills the page, words sit in a clear band over it (top, middle or bottom)
#           "framed" = art in a frame on the upper part of the page, words on the paper below it
#   zones   where words may go on a "full" page, in order of preference (the analysis picks the first clear one)
#   shot    the camera, written into the scene prompt
#   hero    where the hero is added: "left", "center", "right", or None for a page without the hero
#   calm    which part of the picture the scene prompt keeps quiet for words
# ---------------------------------------------------------------------------------------------------------
SHOTS = {
    "wide": "Wide establishing shot; everyone is small in the frame, shown full-length.",
    "medium": "Medium-wide shot; characters full-length, feet on the ground, faces clear.",
    "two": "Medium-wide two-shot; the two characters face each other, full-length, faces clear in three-quarter view.",
    "close": "Close shot framed on hands and the object they hold, with the face partly visible above.",
    "action": "Dynamic wide action shot with strong diagonal movement; characters full-length.",
    "scenery": "Wide scenic shot with no people in the foreground.",
}
CALM = {
    "top": "The top third of the picture is open, simple sky or plain wall with nothing important in it.",
    "bottom": "The bottom third of the picture is plain, simple ground with nothing important in it.",
    "middle": "",
}

TEMPLATE = [
    # n   layout    zones                         shot       hero
    dict(n=1, layout="full", zones=["top", "bottom"], shot="wide", hero="center"),
    dict(n=2, layout="full", zones=["bottom", "top"], shot="medium", hero="left"),
    dict(n=3, layout="full", zones=["top", "bottom"], shot="wide", hero="center"),
    dict(n=4, layout="full", zones=["bottom", "top"], shot="two", hero="left"),
    dict(n=5, layout="framed", zones=[], shot="close", hero="center"),
    dict(n=6, layout="full", zones=["top", "bottom"], shot="medium", hero="right"),
    dict(n=7, layout="full", zones=["bottom", "top"], shot="scenery", hero=None),
    dict(n=8, layout="full", zones=["top", "middle"], shot="wide", hero="center"),
    dict(n=9, layout="framed", zones=[], shot="action", hero="center"),
    dict(n=10, layout="full", zones=["bottom", "top"], shot="scenery", hero=None),
    dict(n=11, layout="full", zones=["top", "bottom"], shot="two", hero="left"),
    dict(n=12, layout="full", zones=["bottom", "top"], shot="medium", hero="right"),
    dict(n=13, layout="full", zones=["top", "bottom"], shot="scenery", hero=None),
    dict(n=14, layout="framed", zones=[], shot="action", hero="center"),
    dict(n=15, layout="full", zones=["bottom", "top"], shot="two", hero="right"),
    dict(n=16, layout="full", zones=["top", "bottom"], shot="scenery", hero=None),
    dict(n=17, layout="full", zones=["top", "middle"], shot="action", hero="left"),
    dict(n=18, layout="framed", zones=[], shot="medium", hero="center"),
    dict(n=19, layout="full", zones=["bottom", "top"], shot="scenery", hero=None),
    dict(n=20, layout="full", zones=["top", "bottom"], shot="wide", hero="center"),
]
for t in TEMPLATE:
    t["calm"] = t["zones"][0] if t["zones"] else None

OPEN_SPACE = {
    "left": "The left third of the picture",
    "center": "The middle of the picture",
    "right": "The right third of the picture",
}
HERO_POSITION = {
    "left": "standing in the left third of the picture",
    "center": "in the middle of the picture",
    "right": "standing in the right third of the picture",
}

# ---------------------------------------------------------------------------------------------------------
# Character bible: every supporting character, drawn once and reused in every scene they appear in.
# ---------------------------------------------------------------------------------------------------------
BIBLE = {
    "jack": {
        "mother": ("Jack's mother", "a tall, grown-up farm woman in her forties with adult height and proportions, "
                   "short curly dark-brown hair under a red headscarf, laugh lines and a strong jaw, wearing a "
                   "mustard-yellow knitted shawl over a long brown wool dress with patched sleeves"),
        "cow": ("Milky-White", "a gentle, thin white dairy cow with soft brown ears and a small brass bell "
                "on a rope collar"),
        "old_man": ("the old man", "a small, twinkly-eyed old man with a long white beard, a patched green "
                    "cloak and a crooked walking stick"),
        "giant": ("the giant", "a huge, burly, fearsome storybook giant with a wild bushy black beard, heavy "
                  "scowling eyebrows, a big crooked nose and a brown leather tunic with a wide belt"),
        "wife": ("the giant's wife", "a very tall, gentle, motherly woman with grey hair in a long braid, rosy "
                 "cheeks, a warm smile and a long green apron"),
        "hen": ("the golden hen", "a plump russet-red hen with a golden comb and a warm golden glow"),
        "harp": ("the golden harp", "a small, ornate golden harp with a carved swirl at the top of its frame "
                 "and shining strings"),
    },
    "red": {
        "mother": ("Red's mother", "a tall, grown-up woman in her thirties with adult height and proportions, dark "
                   "curly hair tied in a yellow scarf, a long sage-green dress and a white apron"),
        "grandma": ("Grandma", "a tiny, round-cheeked grandmother with white hair in a bun, small round "
                    "spectacles, a lavender nightgown and a frilled white nightcap"),
        "wolf": ("the wolf", "the villain of the story: a tall, lanky, menacing wolf who always stands and walks "
                 "upright on his two hind legs like a person, with scruffy dark charcoal-grey fur, a pale grey chest, "
                 "heavy brows over narrowed, glowing amber-yellow eyes, a long snout, big pointed ears, a ragged "
                 "bushy tail, long dark claws and a wicked grin full of sharp white teeth; a classic animated-film "
                 "villain, scary in a storybook way"),
        "woodcutter": ("the woodcutter", "a big, friendly woodcutter with a red-brown beard, a checked flannel "
                       "shirt, suspenders and a wooden-handled tool belt"),
    },
}

HERO = {
    "jack": {
        "role": "Jack",
        "outfit": ("a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers held up "
                   "with a rope belt, and scuffed leather boots"),
        "outfit_skirt": ("a patched oatmeal-colored linen blouse, a brown wool vest, a knee-length rough brown "
                         "wool skirt with a rope belt, thick cream wool stockings, and scuffed leather boots"),
    },
    "red": {
        "role": "Little Red Riding Hood",
        "outfit": ("a bright red hooded cloak worn with the hood down, a cream linen shirt, brown trousers "
                   "and brown boots"),
        "outfit_skirt": ("a bright red hooded cloak worn with the hood down, a cream linen blouse, a "
                         "knee-length blue dress, white stockings and brown boots"),
    },
}

BEANS = ("exactly five plump, glossy magic beans, each a different color: one red, one yellow, one green, "
         "one blue and one purple")

# ---------------------------------------------------------------------------------------------------------
# The stories. Each page: text (printed by the PDF, never drawn), the scene (pre-generated, without the
# hero), cast (bible characters in the scene), and for hero pages what the hero is doing and feeling.
# The hero is called by the story's role name only ("Jack", "Red"), so the words fit any child.
# ---------------------------------------------------------------------------------------------------------
STORIES = {
    "jack": {
        "title": "Jack and the Beanstalk",
        "pages": [
            dict(text="Once upon a time, Jack and Mother lived in a tiny cottage with one old cow, Milky-White.",
                 cast=["mother", "cow"],
                 scene="A tiny thatched cottage in a sunny green valley with a vegetable patch. Jack's mother "
                       "stands by the door, Milky-White grazes by the fence.",
                 action="waving from the garden path", mood="cheerful and hopeful"),
            dict(text="One morning the cupboard was empty. \"We must sell Milky-White,\" said Mother sadly.",
                 cast=["mother"],
                 scene="Inside a bare cottage kitchen with an empty wooden cupboard standing open; Jack's "
                       "mother stands by the table on the right, looking sad.",
                 action="looking up at the mother", mood="worried and a little sad"),
            dict(text="So Jack led Milky-White down the long road to market.",
                 cast=["cow"],
                 scene="A winding dirt road through green fields and hedgerows under a big blue sky; "
                       "Milky-White walks along the road on a rope lead.",
                 action="leading Milky-White by her rope, walking along the road", mood="a little sad about selling her, but determined"),
            dict(text="On the way, Jack met a funny little old man.",
                 cast=["old_man", "cow"],
                 scene="A crossroads with a wooden signpost; the old man stands on the right leaning on his "
                       "stick, Milky-White waits nearby.",
                 action="facing the old man, holding Milky-White's rope", mood="curious"),
            dict(text="\"Five magic beans for your cow,\" he whispered. \"Plant them, and you'll see.\"",
                 cast=["old_man"],
                 scene=f"Close view of the old man's open palm, palm up, holding {BEANS}, each one clearly "
                       "visible against his hand.",
                 action="leaning in close, eyes wide, looking at the beans in the old man's hand",
                 mood="amazed and tempted"),
            dict(text="Jack came home with five beans. \"Beans?\" cried Mother, and out the window they flew!",
                 cast=["mother"],
                 scene=f"Outside the cottage at dusk; Jack's mother, exasperated, leans out of a lit window flinging {BEANS} "
                       "through the air into the garden.",
                 action="standing in the garden, hands on head", mood="stunned and crestfallen"),
            dict(text="That night, while everyone slept, something began to grow.",
                 cast=[],
                 scene="The cottage garden at night under a full moon; a thick green beanstalk twists up out "
                       "of the soil, glowing faintly, leaves unfurling. The cottage windows are dark."),
            dict(text="In the morning, a giant beanstalk reached all the way up into the clouds!",
                 cast=[],
                 scene="Bright morning; an enormous beanstalk beside the cottage rises straight up and "
                       "disappears into fluffy white clouds high above. The garden is quiet and empty.",
                 action="standing at the bottom of the beanstalk, looking up in wonder", mood="astonished"),
            dict(text="Up, up, up climbed Jack, higher than the birds.",
                 cast=[],
                 scene="A view along the giant beanstalk's thick green stem halfway up, among big leaves, with a "
                       "bare, smooth stretch of stem in the middle; the cottage and fields are tiny far below, "
                       "birds fly past.",
                 action="climbing the beanstalk, both hands gripping the stalk", mood="brave and excited"),
            dict(text="At the very top stood a castle in the clouds.",
                 cast=[],
                 scene="A huge grey stone castle with towers standing on a floor of white clouds, the top of "
                       "the beanstalk curling over the edge of the cloud in the foreground."),
            dict(text="A giant woman opened the door. \"Hide quickly,\" she said kindly. \"My husband is coming!\"",
                 cast=["wife"],
                 scene="The enormous castle doorway, wide open; the giant's wife stands tall in the doorway on the "
                       "right holding a big wooden spoon, looking out in surprise.",
                 action="looking up at the giant's wife, tiny next to her", mood="nervous but polite"),
            dict(text="FEE-FI-FO-FUM! The whole castle shook.",
                 cast=["giant"],
                 scene="A giant castle kitchen; the giant stomps through the door on the left, nose in the "
                       "air, sniffing. A huge oven with its door ajar stands on the right.",
                 action="peeking out from behind the oven door", mood="frightened, holding breath"),
            dict(text="The giant counted his gold until he fell fast asleep.",
                 cast=["giant", "hen"],
                 scene="The giant asleep in a huge wooden chair at the table, snoring, with piles of gold "
                       "coins on the table and the golden hen beside them."),
            dict(text="Jack tiptoed to the table and scooped up the hen that laid golden eggs.",
                 cast=["giant", "hen"],
                 scene="The giant's table seen up close; the sleeping giant is in the background, the golden "
                       "hen sits on the table among gold coins.",
                 action="tiptoeing across the table, holding the golden hen in both arms",
                 mood="sneaky and thrilled"),
            dict(text="Then Jack spotted a golden harp that sang all by itself.",
                 cast=["harp"],
                 scene="A shelf in the giant's hall where the golden harp stands glowing, little music "
                       "notes of light floating from its strings.",
                 action="reaching toward the golden harp", mood="enchanted"),
            dict(text="\"MASTER! MASTER!\" cried the harp. The giant woke with a roar.",
                 cast=["giant", "harp"],
                 scene="The giant standing up beside his big wooden chair, wide awake and angry, glaring around "
                       "the room; the golden harp glows on the table."),
            dict(text="Jack raced down the beanstalk as fast as could be, with the giant close behind!",
                 cast=["giant"],
                 scene="The beanstalk against the sky; high above, the giant climbs down the beanstalk, reaching "
                       "downward, leaves shaking.",
                 action="sliding down the beanstalk, holding the golden harp", mood="frightened, eyes wide, racing as fast as possible"),
            dict(text="\"Mother! The axe!\" Jack chopped and chopped.",
                 cast=["mother"],
                 scene="The bottom of the beanstalk beside the cottage; Jack's mother runs up with worried "
                       "eyes.",
                 action="swinging an axe at the base of the beanstalk with both hands", mood="fierce and determined, teeth gritted with effort"),
            dict(text="CRASH! Down came the beanstalk, and that was the end of the giant.",
                 cast=[],
                 scene="The giant beanstalk toppling over across the valley, leaves flying, a big puff of "
                       "dust and clouds; no one is hurt in the picture."),
            dict(text="With the hen, the harp and the gold, Jack and Mother lived happily ever after.",
                 cast=["mother", "cow", "hen", "harp"],
                 scene="The cottage at golden sunset, now with flowers and a new roof; Jack's mother, "
                       "Milky-White, the golden hen and the golden harp in the garden, everyone beaming.",
                 action="laughing in the middle of the family", mood="joyful"),
        ],
    },
    "red": {
        "title": "Little Red Riding Hood",
        "pages": [
            dict(text="Once upon a time, Red lived at the edge of a great green forest.",
                 cast=["mother"],
                 scene="A cozy cottage at the edge of a tall forest on a sunny morning; Red's mother hangs "
                       "washing in the garden.",
                 action="skipping along the garden path", mood="cheerful"),
            dict(text="\"Grandma is poorly,\" said Mother. \"Take her this basket, and stay on the path.\"",
                 cast=["mother"],
                 scene="A bright cottage kitchen; Red's mother stands on the right, smiling warmly, holding out a wicker "
                       "basket with a checked cloth, bread and a jar of honey.",
                 action="taking the basket from Mother", mood="eager and listening"),
            dict(text="So Red set off down the forest path.",
                 cast=[],
                 scene="A winding dirt path into a sun-dappled forest of tall trees, ferns and wildflowers.",
                 action="walking along the path carrying the basket", mood="happy and carefree, mid-skip"),
            dict(text="Before long, Red met a wolf. \"Good morning,\" he said, with a very big smile.",
                 cast=["wolf"],
                 scene="A forest clearing; the wolf stands upright on the right, leaning against a tree, grinning slyly.",
                 action="facing the wolf, holding the basket", mood="polite but unsure"),
            dict(text="\"Why not pick some flowers for Grandma?\" said the wolf.",
                 cast=["wolf"],
                 scene="A patch of bright wildflowers (poppies, daisies and bluebells) at the edge of the path; the "
                       "wolf stands upright on the right, pointing at the flowers with one paw and grinning.",
                 action="holding a small bunch of flowers close, looking at them", mood="tempted"),
            dict(text="Red wandered off the path to pick them, while the wolf ran away fast.",
                 cast=["wolf"],
                 scene="A sunny meadow of flowers beside the forest; in the far background the wolf runs off "
                       "upright between the trees.",
                 action="kneeling in the flowers picking them", mood="dreamy and distracted"),
            dict(text="The wolf raced straight to Grandma's house.",
                 cast=["wolf"],
                 scene="The wolf running upright on his hind legs through the evening forest, fast, ears back, "
                       "toward a little stone cottage with a blue door in the distance."),
            dict(text="At last Red came to Grandma's little cottage.",
                 cast=[],
                 scene="Grandma's small stone cottage with a blue door and roses round it, in a quiet "
                       "forest glade.",
                 action="walking up to the blue door with the basket and flowers", mood="happy to arrive"),
            dict(text="Knock, knock. \"Come in, dear,\" called a strange, croaky voice.",
                 cast=[],
                 scene="The blue cottage door seen close, slightly open, warm light inside.",
                 action="knocking on the door, standing on tiptoe", mood="puzzled"),
            dict(text="Inside, someone was tucked up in Grandma's bed.",
                 cast=["wolf"],
                 scene="Grandma's bedroom; the wolf lies in the bed under the patchwork quilt, wearing Grandma's white frilled cotton nightcap "
                       "and small round spectacles, the quilt pulled up to his snout, a wardrobe in the corner. "
                       "Nobody else is in the room."),
            dict(text="\"Grandma, what big ears you have!\" \"All the better to hear you with.\"",
                 cast=["wolf"],
                 scene="Grandma's bedroom; the wolf lies in the bed on the right under the patchwork quilt, "
                       "wearing Grandma's white frilled cotton nightcap with his big pointed ears poking out of it. He is the only one in the bed, "
                       "and the floor on the left is empty.",
                 action="standing beside the bed holding the basket", mood="suspicious"),
            dict(text="\"Grandma, what big eyes you have!\" \"All the better to see you with.\"",
                 cast=["wolf"],
                 scene="Grandma's bedroom; the wolf lies in the bed on the left under the patchwork quilt, wearing "
                       "Grandma's white frilled cotton nightcap, peering over small round spectacles with huge yellow eyes. The floor on the right is "
                       "empty.",
                 action="leaning back, gripping the basket", mood="worried, eyebrows raised, leaning away"),
            dict(text="\"Grandma, what BIG TEETH you have!\" \"All the better to EAT YOU UP!\"",
                 cast=["wolf"],
                 scene="Grandma's bedroom; the wolf springs up out of the bed onto his hind legs, Grandma's white frilled cotton nightcap flying "
                       "off his head, jaws open wide showing sharp teeth, claws out, the patchwork quilt tumbling."),
            dict(text="Red screamed and ran, round and round the room!",
                 cast=["wolf"],
                 scene="Grandma's bedroom in a muddle, a chair tipped over; in the background the wolf runs "
                       "upright across the room with his arms out.",
                 action="running away, cloak flying", mood="scared"),
            dict(text="Just then, the woodcutter burst through the door.",
                 cast=["woodcutter"],
                 scene="The cottage doorway; the friendly woodcutter steps in on the left, ready to help, "
                       "sunlight behind him.",
                 action="pointing toward the woodcutter, relieved", mood="relieved"),
            dict(text="The wolf leapt out of the window and ran, and he was never seen again.",
                 cast=["wolf"],
                 scene="Outside the stone cottage with the blue door; the wolf tumbles out of the open window "
                       "and lands running upright toward the forest, ears flat, looking back in alarm."),
            dict(text="Out of the wardrobe stepped Grandma, safe and sound!",
                 cast=["grandma", "woodcutter"],
                 scene="Grandma's bedroom; Grandma steps out of the open wardrobe on the left in her "
                       "nightgown and cap, smiling with relief, the woodcutter smiling by the door.",
                 action="running to hug Grandma", mood="overjoyed"),
            dict(text="They shared the bread and honey, and Grandma felt better at once.",
                 cast=["grandma", "woodcutter"],
                 scene="A cozy table by the fire with bread, honey and tea; Grandma sits on the left, "
                       "the woodcutter on the right.",
                 action="sitting at the table between them, sharing bread", mood="happy and cozy"),
            dict(text="Far away over the hills, the wolf kept running.",
                 cast=["wolf"],
                 scene="Rolling green hills at sunset; the small figure of the wolf runs upright away into the "
                       "distance."),
            dict(text="And from that day on, Red always stayed on the path.",
                 cast=["mother", "grandma"],
                 scene="The forest path at golden sunset with Red's mother and Grandma waving together "
                       "beside the path.",
                 action="walking happily along the middle of the path, waving", mood="content and smiling, a little wiser"),
        ],
    },
}

# How each character looks in their bible portrait (their usual self).
PORTRAIT_EXPRESSION = {
    ("red", "wolf"): "a wicked, scheming sneer with narrowed eyes",
    ("jack", "giant"): "a deep, suspicious scowl",
    ("jack", "old_man"): "a mysterious, knowing twinkle",
    ("jack", "cow"): "gentle and calm",
    ("red", "grandma"): "a warm, kindly smile",
    ("red", "woodcutter"): "a brave, steady look",
}

# What each supporting character feels on each page. Without this the model gives everyone the same pleasant
# face; the check scores every one of these.
FEELINGS = {
    ("jack", 1): {"mother": "warm and hopeful, smiling", "cow": "calm and content"},
    ("jack", 2): {"mother": "sad and worried, brow furrowed, shoulders slumped"},
    ("jack", 3): {"cow": "sad and droopy, ears down, head low"},
    ("jack", 4): {"old_man": "mysterious, with a sly twinkle in his eye", "cow": "uneasy, ears back"},
    ("jack", 5): {"old_man": "sly and knowing, a secretive smile"},
    ("jack", 6): {"mother": "exasperated and angry, eyes squeezed, mouth open in a shout"},
    ("jack", 11): {"wife": "startled and worried, eyebrows up"},
    ("jack", 12): {"giant": "suspicious and menacing, nose in the air sniffing, eyes narrowed, scowling"},
    ("jack", 13): {"giant": "fast asleep, mouth open, snoring", "hen": "drowsy"},
    ("jack", 14): {"giant": "fast asleep, snoring", "hen": "startled, feathers puffed"},
    ("jack", 15): {"harp": "glowing softly"},
    ("jack", 16): {"giant": "furious and fearsome, brows crashing down, fists clenched",
                   "harp": "alarmed, glowing bright"},
    ("jack", 17): {"giant": "furious and fearsome, roaring, reaching down with a huge hand"},
    ("jack", 18): {"mother": "frightened but brave, eyes wide, hands up"},
    ("jack", 20): {"mother": "overjoyed, laughing", "cow": "happy", "hen": "proud and happy", "harp": "glowing warmly"},
    ("red", 1): {"mother": "cheerful, humming as she works"},
    ("red", 2): {"mother": "kind but a little concerned, gently serious"},
    ("red", 4): {"wolf": "falsely friendly: a wide fake smile, but cold, narrowed, hungry eyes"},
    ("red", 5): {"wolf": "wicked and scheming, a sly sideways grin, eyes glinting"},
    ("red", 6): {"wolf": "sinister and eager, grinning over his shoulder as he hurries away"},
    ("red", 7): {"wolf": "hungry and menacing, eyes glowing, tongue licking his lips"},
    ("red", 10): {"wolf": "smug and cunning, glowing eyes peeking over the quilt"},
    ("red", 11): {"wolf": "sly and sneaky, a sickly-sweet fake smile, one ear twitching"},
    ("red", 12): {"wolf": "menacing, huge hungry glowing eyes staring over the spectacles"},
    ("red", 13): {"wolf": "terrifying in a storybook way: jaws wide, sharp teeth bared, claws out, eyes blazing"},
    ("red", 14): {"wolf": "hungry and menacing, snarling, claws reaching"},
    ("red", 15): {"woodcutter": "brave and determined, a stern frown"},
    ("red", 16): {"wolf": "terrified, ears flat, eyes wide with fear, fleeing"},
    ("red", 17): {"grandma": "overjoyed and relieved, arms open", "woodcutter": "kind, a proud smile"},
    ("red", 18): {"grandma": "happy and cozy, laughing", "woodcutter": "cheerful"},
    ("red", 19): {"wolf": "frightened and defeated, tail between his legs"},
    ("red", 20): {"mother": "relieved and happy, waving", "grandma": "happy, waving"},
}


def _feelings(story, p):
    f = FEELINGS.get((story, p["n"]), {})
    if not f:
        return ""
    parts = [f"{BIBLE[story][c][0]} looks {mood}" for c, mood in f.items()]
    return ("Expressions, big and easy to read like an animated feature film: " + "; ".join(parts) + ". ")


# Attach template slots so every page knows its layout.
for _key, _story in STORIES.items():
    assert len(_story["pages"]) == len(TEMPLATE) == 20, _key
    for _i, (_p, _t) in enumerate(zip(_story["pages"], TEMPLATE), start=1):
        _p.update(n=_i, **{k: v for k, v in _t.items() if k != "n"})
        assert (_p["hero"] is None) == ("action" not in _p), (_key, _i)
        for _c in _p["cast"]:
            assert _c in BIBLE[_key], (_key, _i, _c)

STORY_KEYS = list(STORIES)
# Characters drawn from their written description in every scene, with no portrait in the bible (a last resort
# if no image model will draw them).
TEXT_ONLY = set()          # none at the moment: the bible portraits now fall back to other image models
TEXT_ONLY_NOTE = ("Not drawn as a portrait: OpenAI's image safety filter refused it every time, so each scene "
                  "draws this character from the description instead.")


def text_only(story, key):
    return (story, key) in TEXT_ONLY
HERO_PAGES = {k: [p["n"] for p in s["pages"] if p["hero"]] for k, s in STORIES.items()}


# ---------------------------------------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------------------------------------
def bible_prompt_plain(story, key):
    """A shorter second wording, tried if the first is refused."""
    _, desc = BIBLE[story][key]
    return (f"Children's picture-book illustration in a 3D animated style: {desc}, standing, full length, "
            f"{PORTRAIT_EXPRESSION.get((story, key), 'a calm, natural expression')}, on a plain white background.")


def bible_prompt(story, key):
    # The family label ("Jack's mother") is left out on purpose: paired with "full-body view of a woman" it was
    # refused by the image model's safety filter every time. The description alone draws the same character.
    _, desc = BIBLE[story][key]
    return (f"Art style: {STYLE} A character model sheet for a picture book, showing one supporting character: "
            f"{desc}. One full-body view "
            f"standing, facing the viewer at a slight three-quarter angle, centered, on a plain light background. "
            f"Expression: {PORTRAIT_EXPRESSION.get((story, key), 'a calm, natural expression')}. {HANDS} {NO_WORDS}")


def bible_from_scene_prompt(story, key):
    _, desc = BIBLE[story][key]
    return (f"Art style: {STYLE} Image 1 is a page from a picture book. Make a character model sheet of the "
            f"character in this picture who is {desc}: the same character with the same face, hair, clothes and colors, alone, "
            f"one full-body view standing, centered, on a plain light background. {HANDS} {NO_WORDS}")


def _no_hero_names(story, text):
    role = {"jack": "Jack", "red": "Red"}[story]
    return text.replace(f"{role}'s mother", "the mother").replace(f"{role}'s Mother", "the mother")


REFS_SENTENCE = " The reference images show the characters in this scene; draw them exactly as they look there."


def scene_prompt(story, p):
    cast = " ".join(f"{BIBLE[story][c][0].capitalize()} is {BIBLE[story][c][1]}." for c in p["cast"])
    refs = REFS_SENTENCE if [c for c in p["cast"] if not text_only(story, c)] else ""
    # Hero pages get a stand-in child on purpose, in the hero's place, pose and costume. Leaving the spot
    # empty never worked: the model kept drawing a child anyway, just in the wrong place and clothes. Each
    # book then swaps the stand-in for the real child (insert_prompt), keeping the pose.
    if p["hero"]:
        who = (f" One stand-in child is {HERO_POSITION[p['hero']]}, {p['action']}, full-length with the face "
               f"clearly visible, wearing {HERO[story]['outfit']}; the child feels {p['mood']}. The only figures "
               "in the picture are this one child and the characters named here.")
    else:
        who = " Every figure in the picture is one of the characters named here."
    calm = CALM.get(p["calm"] or "", "")
    # The hero's name never appears in a scene prompt ("Jack's mother" -> "the mother"): any mention of the hero
    # invites the model to draw one.
    scene = _no_hero_names(story, p["scene"])
    cast = _no_hero_names(story, cast)
    return (f"Art style: {STYLE} A full-bleed page from a 3D animated picture book of a classic fairy tale. "
            f"Scene: {scene}{refs} {cast}{who} "
            f"{_feelings(story, p)}"
            f"{SHOTS[p['shot']]} {calm} {HANDS} "
            f"Art style, again: {STYLE} {NO_WORDS}")


def hero_prompt(story):
    h = HERO[story]
    return (f"Art style: {STYLE} A character model sheet on one plain light background for the hero of a picture "
            f"book, {h['role']}. LEFT HALF: a large head-and-shoulders close-up of the person in this photo as "
            "the hero, facing the viewer, the face filling most of that half, crisp and detailed. Keep their real "
            "face shape, eye shape, nose, mouth, eyebrows, skin tone, hair color, hair length, hairstyle, glasses "
            "if any, and their real age, so family would recognize them at a glance. Stylize the rendering, not "
            "the anatomy. Neutral, relaxed expression with the mouth closed. RIGHT HALF: the same hero full-length, "
            "head to toe, facing the viewer. "
            f"If the person in the photo is a girl or a woman, the hero wears {h['outfit_skirt']}; otherwise the "
            f"hero wears {h['outfit']}. The same outfit in both views. {HANDS} {NO_WORDS}")


def insert_prompt(story, p):
    h = HERO[story]
    return (f"Art style: {STYLE} Image 1 is a finished page from a 3D animated picture book. Image 2 is the "
            f"character sheet of the hero, {h['role']}. Image 1 has a stand-in child {HERO_POSITION[p['hero']]}, "
            f"{p['action']}. Replace that stand-in child with the hero from image 2, in the same place and the same "
            f"pose, so the hero is the only child in the picture. The hero is the exact character from image 2: "
            "the same face, hair, skin tone, age, "
            "body proportions and outfit, an unmistakable match, with the face clearly visible. Draw the hero in "
            "the same 3D rendering, lighting and scale as image 1, full-length with feet on the ground where "
            f"standing. The hero feels {p['mood']}, and it shows clearly on the face, in the eyebrows, eyes and "
            f"mouth, and in the body language: a big, easy-to-read expression like an animated feature film. Keep everything else in "
            f"image 1 as it is: the setting, the other characters and the composition. "
            f"{CALM.get(p['calm'] or '', '')} {HANDS} {NO_WORDS}")


def analysis_prompt(story, p, has_hero):
    who = (f"Image 2 is the character sheet of the hero, {HERO[story]['role']}. " if has_hero else "")
    cast = ", ".join(BIBLE[story][c][0] for c in p["cast"]) or "no supporting characters"
    beat = p["scene"] + (f" The hero is {p['action']}, feeling {p['mood']}." if has_hero else "") + \
        (" " + _feelings(story, p) if FEELINGS.get((story, p["n"])) else "")
    return (
        "You are the quality checker for a children's picture book. Image 1 is one generated page. " + who +
        f"The page should show: {beat} Characters who should appear: {cast}"
        + (" and the hero" if has_hero else "") + ".\n"
        "Score each from 0 to 10, strictly:\n"
        "- hero: " + ("the hero in image 1 is clearly the same person as image 2 (face, hair, skin, glasses, "
                      "outfit); 0 if the hero is missing or a different person" if has_hero else "always 10") + "\n"
        "- story: the picture shows what the page should show, with the right characters and no extra people"
        + ("; there must be exactly one child, the hero; a second child anywhere scores 0" if has_hero else "")
        + "\n"
        "- anatomy: hands have five fingers, no extra or merged limbs, faces are not distorted\n"
        "- clean: no letters, words, signatures, watermarks, borders, collage panels or broken artifacts\n"
        "- expression: " + (f"the hero's face clearly shows '{p['mood']}' (eyebrows, eyes, mouth), and every other "
                            "character shows the feeling listed for them; a generic smile where the page calls "
                            "for worry, fear, menace or surprise scores 3 or less" if has_hero else
                            "every character shows the feeling listed for them, clearly; a bland or pleasant face "
                            "where the page calls for menace, fear or anger scores 3 or less") + "\n"
        "Then map where the faces and the important story things are, on a 3x3 grid (rows top/middle/bottom, "
        "columns left/center/right): mark a cell true if a face, an eye, a hand doing something, or an object "
        "the reader must see is in it; false if it is only sky, wall, floor, grass, foliage or other background.\n"
        "Reply with only JSON: {\"hero\":int,\"story\":int,\"anatomy\":int,\"clean\":int,\"expression\":int,"
        "\"issues\":[short strings],\"busy\":{\"top\":[bool,bool,bool],\"middle\":[bool,bool,bool],"
        "\"bottom\":[bool,bool,bool]}}"
    )
