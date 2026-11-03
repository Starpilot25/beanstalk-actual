"""
The book, as data.

Every image call is built from the same three ingredients, in the same order:
    STYLE (never changes)  +  CAST (never changes)  +  one PAGE entry
so the child, the mother, the cow and the art style stay the same from page to page.

To add page 4 (the beanstalk at dawn) and beyond, append to PAGES. Nothing else changes.
"""

# The house style for the whole book. Word for word, in every call. Never edit mid-book.
STYLE = "Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light."

# Fixed descriptions, reused word for word in every call so characters don't drift.
JACK_OUTFIT = ("a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers "
               "held up with a rope belt, and scuffed leather boots")
CAST = {
    "jack": ("Jack is the exact character on the reference sheet (the large close-up on the left and the "
             "top-left full-body view), an unmistakable match: the same face "
             "shape, eyes, nose, mouth, eyebrows, hair, skin tone, apparent age and body proportions, "
             f"wearing {JACK_OUTFIT}."),
    "mother": ("Jack's mother is a thin, careworn woman in her forties with auburn hair in a loose bun, "
               "a faded blue dress and a cream apron."),
    "cow": ("Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell "
            "on a rope collar."),
    "old_man": ("The old man is small and twinkly-eyed, with a long white beard, a patched green cloak "
                "and a crooked walking stick."),
}

# The reference image is a cast sheet: Jack's face close-up on the left, and full-body views of the
# characters who recur (Jack, his mother, Milky-White) on the right. One-off characters like the old
# man (page 2 only) are drawn from their written description. One image, reused on every page.
CAST_SHEET = ("The reference image is the cast sheet for this book. Draw every character who is on the "
              "sheet exactly as they look there - same face, build, colors and clothes. Characters who "
              "are not on the sheet follow their written description. Draw only the characters this "
              "scene names.")

# The five magic beans, described the same way on every page they appear. Five named colors are
# five distinct objects to draw, which models get right far more often than "five beans".
BEANS = ("exactly five plump, glossy magic beans, each a different color: one red, one yellow, one green, "
         "one blue and one purple")

# Hands are the most common failure (extra or merged fingers). Same sentence in every call,
# worded as what we want; each page also keeps its hand poses simple.
HANDS = ("Every hand is anatomically correct: one thumb and four fingers, natural proportions, "
         "fingers clearly separated.")

# Where the story text goes, and how the picture keeps that area calm.
# The image model is never asked to draw any words; the PDF layer adds them.
ZONES = {
    "bottom": ("Wide shot: characters are shown full-length, feet on the ground, standing far enough back "
               "that every character, face and important object sits in the upper two-thirds of the frame; "
               "the bottom third is only plain, simple ground in front of them."),
    "top": ("Wide shot: every character, face and important object sits in the lower two-thirds of the "
            "frame, and the top third is only open, simple sky."),
}

PAGES = [
    {
        "n": 1,
        "title": "The empty cupboard",
        "text": "Jack and his mother had nothing left to sell but Milky-White.",
        "cast": ["jack", "mother", "cow"],
        "scene": ("Inside a bare cottage kitchen with an empty wooden cupboard standing open. Jack and his "
                  "mother stand together near the table. Through the open door at the back, Milky-White "
                  "is visible standing in the yard."),
        "shot": ("Jack and his mother stand toward the back of the room, shown full-length from head to toe with both feet planted on the floorboards. Jack shows "
                 "his full face toward the viewer, warmly front-lit, his eyes turned to his mother. Warm "
                 "daylight palette. The floor in front of them is plain, bare wooden floorboards."),
        "hands": "Jack's hands rest at his sides; his mother's hand rests flat on his shoulder.",
        "mood": ("Mood: worried and a little sad. Jack's brow is creased and his mouth turned slightly down; "
                 "his mother looks tired and anxious, one hand on his shoulder. Nobody is smiling."),
        "zone": "bottom",
        "text_color": "light",   # light lettering on a soft dark fade
    },
    {
        "n": 2,
        "title": "The trade",
        "text": "Five magic beans, said the old man. For one cow.",
        "cast": ["jack", "old_man", "cow"],
        "scene": ("A dirt road through green fields on the way to market. The old man holds out his open "
                  "palm with " + BEANS + ", spaced apart so each one is clearly visible. Jack holds Milky-White's rope."),
        "shot": ("Jack is in three-quarter view, face clearly visible, looking at the beans. Bright "
                 "midday palette. The top third is open pale-blue sky with a few soft clouds."),
        "hands": ("The old man's open hand faces palm-up toward the viewer, large and clear, with the five "
                  "beans resting in it; Jack's hand is closed around Milky-White's rope."),
        "mood": ("Mood: curious and tempted. Jack leans in, eyes wide with wonder at the beans, lips parted; "
                 "the old man wears a sly, knowing half-smile."),
        "zone": "top",
        "text_color": "dark",    # dark lettering on light sky
    },
    {
        "n": 3,
        "title": "Out the window",
        "text": "Beans! she cried. And out the window they went.",
        "cast": ["jack", "mother"],
        "scene": ("The outside of the small thatched cottage at dusk. Jack's mother leans out of a lit "
                  "window, flinging " + BEANS + ", large enough to see, scattering through the air into the garden below. Jack "
                  "stands in the open doorway, watching."),
        "shot": ("Jack is in the doorway, face clearly visible and lit by the warm light from inside. "
                 "Darker dusk palette of deep blues and purples, darker than daytime. The lower third is "
                 "dark, shadowed grass."),
        "hands": "Jack's hands hold the edge of the door frame; his mother's arm swings out of the window.",
        "mood": ("Mood: anger and dismay. His mother's face is furious, mouth open mid-shout, as she flings "
                 "the beans; Jack looks stunned and crestfallen, shoulders slumped."),
        "zone": "bottom",
        "text_color": "light",
    },
    # Page 4 - the beanstalk at dawn - goes here next. The planting and climbing scenes from the
    # previous assignment become later pages in the same format.
]

PAGES_BY_N = {p["n"]: p for p in PAGES}
