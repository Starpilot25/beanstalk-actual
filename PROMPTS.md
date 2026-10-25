# How the prompts are built and tested

The prompt is the thing being engineered here. This file is the record: what each call sends,
what went wrong, and what changed. **Fill in the log as you test in the OpenAI Playground.**

## The rule for every call
`STYLE` + `CAST` + one page entry, all from `storyboard.py`. The style string is identical in every call:

> Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light.

Jack's reference image (made once from the photo) is the only image sent with each page.

## Testing a prompt in the Playground (before it goes in the code)
1. platform.openai.com → **Playground → Images**. Pick `gpt-image-1-mini` (the model the app uses).
2. For Jack: upload a photo, choose **Edit**, paste the hero prompt below.
3. For a page: upload the Jack image you got, choose **Edit**, paste that page's prompt.
4. Look at the result against the checklist. Write down what was wrong.
5. Hand the prompt *and* what was wrong to an AI model (prompt below), apply its fix, and run it again.
6. Only when it works in the Playground, copy the change into `storyboard.py` / `app.py`.

### Asking an AI to improve a prompt
> I'm generating picture-book pages with an image model. Here is my prompt: [paste].
> Here is what came out wrong: [e.g. "Jack's face is different from the reference", "the cow is brown",
> "words appeared on the cupboard"]. Rewrite the prompt to fix only that. Keep the style sentence
> exactly as it is. Describe what should be in the picture rather than naming what shouldn't be,
> because naming an object tends to make the model draw it.

## Lessons already learned (from the last assignment)
- **Don't name what you don't want.** "Keep the glasses" put glasses on people who don't wear any.
  "No beanstalk has grown yet" put a beanstalk in the planting scene. Describe what *is* there instead.
- **Don't ask the model for words.** Even "leave room for text" can produce garbled letters.
  The prompt only asks for a calm, simple area; the PDF adds the words.
- **Stylize the rendering, not the anatomy.** "Large expressive eyes" is the required style, but
  pushed too far it produced bug-eyed, creepy faces. The hero prompt keeps the child's real
  proportions and a calm expression to balance it.
- **One reference, not two.** Sending both the photo and a cartoon gave double features
  (two noses). Pages now get only the Jack reference.

## Checklist for each result
- Jack's face matches the reference (and the photo): face shape, hair, skin tone, eyes, age
- Same clothes as the reference
- Everything in the scene description is there; nothing extra (no lettering anywhere)
- The text area (lower third / sky / dark grass) is calm enough to read words over
- Page 3 is clearly darker than pages 1–2
- The mother and the cow look the same on every page they appear on

## Log
| Date | Call | What was wrong | Change made | Better? |
|---|---|---|---|---|
| | hero | | | |
| | page 1 | | | |
| | page 2 | | | |
| | page 3 | | | |

## The prompts the app sends today
Generated from the code (`python -c "import app; ..."`), so they match exactly.

**Jack (hero)** — image: the photo
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. Turn the child in this photo into the hero of a picture book: a full-body character reference, standing, facing the viewer, arms relaxed, on a plain light background. Keep their real face shape, eye shape, nose, mouth, eyebrows, skin tone, hair color, hair length and hairstyle, and their real age, so family would recognize them at a glance. Stylize the rendering, not the anatomy. Calm, friendly expression. Dress them as Jack, in a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers held up with a rope belt, and scuffed leather boots. Pure illustration with no lettering anywhere.
```

**Page 1 — the empty cupboard** — image: Jack
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed picture-book illustration. Jack is the child in the reference image: the same face, hair, skin tone, eye color, age and body as in the reference, wearing a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers held up with a rope belt, and scuffed leather boots. Jack's mother is a thin, kind-faced woman in her forties with auburn hair in a loose bun, a faded blue dress and a cream apron. Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell on a rope collar. Draw Jack exactly as in the reference image every time - same face, same hair, same clothes. Scene: Inside a bare cottage kitchen with an empty wooden cupboard standing open. Jack and his mother stand together near the table. Through the open door at the back, Milky-White is visible standing in the yard. Jack shows his full face toward the viewer, warmly front-lit, his eyes turned to his mother. Warm daylight palette. The lower third is plain, empty wooden floorboards. Keep the bottom third of the picture calm and simple, with no characters or detailed objects in it. Pure illustration with no lettering anywhere.
```

**Page 2 — the trade** — image: Jack
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed picture-book illustration. Jack is the child in the reference image: the same face, hair, skin tone, eye color, age and body as in the reference, wearing a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers held up with a rope belt, and scuffed leather boots. The old man is small and twinkly-eyed, with a long white beard, a patched green cloak and a crooked walking stick. Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell on a rope collar. Draw Jack exactly as in the reference image every time - same face, same hair, same clothes. Scene: A dirt road through green fields on the way to market. The old man holds out his open palm with five shiny beans, each a different color. Jack holds Milky-White's rope. Jack is in three-quarter view, face clearly visible, looking at the beans. Bright midday palette. The top third is open pale-blue sky with a few soft clouds. Keep the top third of the picture calm and simple, with no characters or detailed objects in it. Pure illustration with no lettering anywhere.
```

**Page 3 — out the window** — image: Jack
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed picture-book illustration. Jack is the child in the reference image: the same face, hair, skin tone, eye color, age and body as in the reference, wearing a patched oatmeal-colored linen shirt, a brown wool vest, rough brown trousers held up with a rope belt, and scuffed leather boots. Jack's mother is a thin, kind-faced woman in her forties with auburn hair in a loose bun, a faded blue dress and a cream apron. Draw Jack exactly as in the reference image every time - same face, same hair, same clothes. Scene: The outside of the small thatched cottage at dusk. Jack's mother leans out of a lit window, flinging the beans, which scatter through the air into the garden below. Jack stands in the open doorway, watching. Jack is in the doorway, face clearly visible and lit by the warm light from inside. Darker dusk palette of deep blues and purples, darker than daytime. The lower third is dark, shadowed grass. Keep the bottom third of the picture calm and simple, with no characters or detailed objects in it. Pure illustration with no lettering anywhere.
```
