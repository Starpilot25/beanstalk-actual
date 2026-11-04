# How the prompts are built and tested

The prompt is the thing being engineered here. This file is the record: what each call sends,
what went wrong, and what changed. **Fill in the log as you test in the OpenAI Playground.**

## The rule for every call
`STYLE` + `CAST` + one page entry, all from `storyboard.py`. The style string is identical in every call:

> Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light.

The cast sheet (made once from the photo) is the only image sent with each page.

## Testing a prompt in the Playground (before it goes in the code)
1. platform.openai.com → **Playground → Images**. Pick `gpt-image-2.5-flare` at **medium** (the model the app uses for pages).
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
| Oct 25 | page 1 (gpt-image-2.5-flare) | Came out as a flat 2D painted storybook, not 3D; Jack became a generic younger kid; Jack and mother filled the bottom third, so the words covered Jack | Tied the rendering to the 3D Jack reference ("rendered exactly like the reference image") and repeated the style sentence at the end; Jack is now "the exact character in the reference image" instead of "the child"; the text zone now says where characters *are* (upper two-thirds, head to knees) | test next |
| Oct 25 | pages vs. photo | Step-1 Jack looked like me, but the pages didn't: the full-body reference has a tiny face, so the page model had little to copy and drew a generic face | Jack is now a character sheet: a large face close-up on the left plus full body in costume on the right, still one reference image. Pages are told to match the close-up | test next |
| Oct 25 | all pages | Every result so far came from `gpt-image-1-mini` at **low** quality (the model switch hadn't applied): waxy, plastic 3D, wrong actions, characters filling the frame | Switched to `gpt-image-2.5-flare`, pages at **medium**. Huge improvement: real 3D storybook look, correct cast, cow with bell in the doorway | yes |
| Oct 25 | page 1 | Jack and mother cut off at the knees, so they looked like they were sinking into the floor | My "seen from head to knees" was taken literally. Now "full-length, head to toe, feet planted on the floorboards", standing toward the back so they stay above the text | test next |
| Oct 25 | all pages | Everyone always smiling, even on the sad and angry pages | Nothing in the prompt set a mood, the Jack sheet asked for a "friendly expression", and the mother was "kind-faced". Added a mood line per page (worried, tempted, furious and stunned), "his expression follows this page's mood", a neutral expression on the Jack sheet, and "careworn" instead of "kind-faced" | test next |
| Oct 25 | pages 1–2 | Milky-White looked different on page 1 and page 2 | Only Jack had a reference image; the cow was redrawn from text each time. The Jack sheet is now a cast sheet (face close-up on the left; full-body Jack, mother, cow and old man in a grid on the right), still one image, made at medium quality. Pages are told to copy every character from it and draw only the ones the scene names | test next |
| Oct 26 | all pages | Wrong number of fingers | Added one hands sentence to every page ("one thumb and four fingers... clearly separated", worded positively) and a simple hand pose per page (hands at sides, gripping a rope or the door frame; the old man's palm big and clear). (A one-click Fix hands button was tried and removed, so people can't burn through image credits; "Change it" can still repair hands) | test next |
| Oct 26 | pages 2–3 | Inconsistent number of beans (the story says five) | Page 3 only said "the beans", and page 2's "five beans" asks the model to count. Both pages now use one fixed description: exactly five beans in five named colors (red, yellow, green, blue, purple), spaced apart / large enough to see. Five named objects are easier to get right than a number, and they stay the same beans across pages | test next |
| Nov 2 | cast sheet | The old man was on the sheet but appears only on page 2, taking space from the characters who recur | Removed him from the sheet (now Jack's face close-up + full-body Jack and mother side by side, cow below). Page 2 draws him from his fixed description; the sheet instructions now say characters not on the sheet follow their description | test next |
| Nov 4 | cast sheet + pages | Girls and women were always put in Jack's trousers | The cast sheet now picks the outfit from the photo: a girl or woman gets a matching skirt version (linen blouse, brown wool vest, knee-length wool skirt with a rope belt, wool stockings, boots), anyone else the trousers. Pages no longer spell out the trousers; they copy the clothes from the sheet, so every page matches the sheet | test next |
| | hero | | | |
| | page 1 | | | |
| | page 2 | | | |
| | page 3 | | | |

## The prompts the app sends today
Generated from the code, so they match exactly.

**Cast sheet** — image: the photo
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. Create the cast reference sheet for a picture book, on one plain light background. LEFT HALF: a large head-and-shoulders close-up of the person in this photo as the hero, Jack, facing the viewer, the face filling most of that half, crisp and detailed. Keep their real face shape, eye shape, nose, mouth, eyebrows, skin tone, hair color, hair length and hairstyle, and their real age, so family would recognize them at a glance. Stylize the rendering, not the anatomy. Neutral, relaxed expression with the mouth closed. RIGHT HALF: full-body views of the recurring cast. Across the top, the same Jack and Jack's mother standing side by side, facing the viewer, head to toe; across the bottom, Milky-White the cow standing in side view. Jack's mother is a thin, careworn woman in her forties with auburn hair in a loose bun, a faded blue dress and a cream apron. Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell on a rope collar. Pure illustration with no lettering anywhere.
```

**Page 1 — the empty cupboard** — image: the cast sheet
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed frame from a 3D computer-animated film, rendered exactly like the reference image: the same 3D modeling, materials, shading and lighting, with soft rounded 3D forms. The reference image is the cast sheet for this book. Draw every character who is on the sheet exactly as they look there - same face, build, colors and clothes. Characters who are not on the sheet follow their written description. Draw only the characters this scene names. Jack is the exact character on the reference sheet (the large close-up on the left and the top-left full-body view), an unmistakable match: the same face shape, eyes, nose, mouth, eyebrows, hair, skin tone, apparent age and body proportions, wearing exactly the clothes from the reference sheet: the patched oatmeal-colored linen top, brown wool vest, rope belt and scuffed leather boots, with the same trousers or skirt as on the sheet. Jack's mother is a thin, careworn woman in her forties with auburn hair in a loose bun, a faded blue dress and a cream apron. Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell on a rope collar. Match Jack's face to the reference sheet, but his expression follows this page's mood. Scene: Inside a bare cottage kitchen with an empty wooden cupboard standing open. Jack and his mother stand together near the table. Through the open door at the back, Milky-White is visible standing in the yard. Jack and his mother stand toward the back of the room, shown full-length from head to toe with both feet planted on the floorboards. Jack shows his full face toward the viewer, warmly front-lit, his eyes turned to his mother. Warm daylight palette. The floor in front of them is plain, bare wooden floorboards. Jack's hands rest at his sides; his mother's hand rests flat on his shoulder. Every hand is anatomically correct: one thumb and four fingers, natural proportions, fingers clearly separated. Mood: worried and a little sad. Jack's brow is creased and his mouth turned slightly down; his mother looks tired and anxious, one hand on his shoulder. Nobody is smiling. Wide shot: characters are shown full-length, feet on the ground, standing far enough back that every character, face and important object sits in the upper two-thirds of the frame; the bottom third is only plain, simple ground in front of them. Art style, again: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. Pure illustration with no lettering anywhere.
```

**Page 2 — the trade** — image: the cast sheet
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed frame from a 3D computer-animated film, rendered exactly like the reference image: the same 3D modeling, materials, shading and lighting, with soft rounded 3D forms. The reference image is the cast sheet for this book. Draw every character who is on the sheet exactly as they look there - same face, build, colors and clothes. Characters who are not on the sheet follow their written description. Draw only the characters this scene names. Jack is the exact character on the reference sheet (the large close-up on the left and the top-left full-body view), an unmistakable match: the same face shape, eyes, nose, mouth, eyebrows, hair, skin tone, apparent age and body proportions, wearing exactly the clothes from the reference sheet: the patched oatmeal-colored linen top, brown wool vest, rope belt and scuffed leather boots, with the same trousers or skirt as on the sheet. The old man is small and twinkly-eyed, with a long white beard, a patched green cloak and a crooked walking stick. Milky-White is a gentle, thin white dairy cow with soft brown ears and a small brass bell on a rope collar. Match Jack's face to the reference sheet, but his expression follows this page's mood. Scene: A dirt road through green fields on the way to market. The old man holds out his open palm with exactly five plump, glossy magic beans, each a different color: one red, one yellow, one green, one blue and one purple, spaced apart so each one is clearly visible. Jack holds Milky-White's rope. Jack is in three-quarter view, face clearly visible, looking at the beans. Bright midday palette. The top third is open pale-blue sky with a few soft clouds. The old man's open hand faces palm-up toward the viewer, large and clear, with the five beans resting in it; Jack's hand is closed around Milky-White's rope. Every hand is anatomically correct: one thumb and four fingers, natural proportions, fingers clearly separated. Mood: curious and tempted. Jack leans in, eyes wide with wonder at the beans, lips parted; the old man wears a sly, knowing half-smile. Wide shot: every character, face and important object sits in the lower two-thirds of the frame, and the top third is only open, simple sky. Art style, again: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. Pure illustration with no lettering anywhere.
```

**Page 3 — out the window** — image: the cast sheet
```
Art style: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. A full-bleed frame from a 3D computer-animated film, rendered exactly like the reference image: the same 3D modeling, materials, shading and lighting, with soft rounded 3D forms. The reference image is the cast sheet for this book. Draw every character who is on the sheet exactly as they look there - same face, build, colors and clothes. Characters who are not on the sheet follow their written description. Draw only the characters this scene names. Jack is the exact character on the reference sheet (the large close-up on the left and the top-left full-body view), an unmistakable match: the same face shape, eyes, nose, mouth, eyebrows, hair, skin tone, apparent age and body proportions, wearing exactly the clothes from the reference sheet: the patched oatmeal-colored linen top, brown wool vest, rope belt and scuffed leather boots, with the same trousers or skirt as on the sheet. Jack's mother is a thin, careworn woman in her forties with auburn hair in a loose bun, a faded blue dress and a cream apron. Match Jack's face to the reference sheet, but his expression follows this page's mood. Scene: The outside of the small thatched cottage at dusk. Jack's mother leans out of a lit window, flinging exactly five plump, glossy magic beans, each a different color: one red, one yellow, one green, one blue and one purple, large enough to see, scattering through the air into the garden below. Jack stands in the open doorway, watching. Jack is in the doorway, face clearly visible and lit by the warm light from inside. Darker dusk palette of deep blues and purples, darker than daytime. The lower third is dark, shadowed grass. Jack's hands hold the edge of the door frame; his mother's arm swings out of the window. Every hand is anatomically correct: one thumb and four fingers, natural proportions, fingers clearly separated. Mood: anger and dismay. His mother's face is furious, mouth open mid-shout, as she flings the beans; Jack looks stunned and crestfallen, shoulders slumped. Wide shot: characters are shown full-length, feet on the ground, standing far enough back that every character, face and important object sits in the upper two-thirds of the frame; the bottom third is only plain, simple ground in front of them. Art style, again: Modern 3D animated feature — rounded forms, large expressive eyes, soft rim light. Pure illustration with no lettering anywhere.
```
