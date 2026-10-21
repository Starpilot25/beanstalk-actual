# Production test log

Two things must hold for every upload:
1. **Likeness** — someone who knows the person would recognize them in the cartoon and in both scenes.
2. **Scene fidelity** — every element in the caption is visible in the image.

## Test set (use at least 5, not just yourself — with permission)
Cover variety so a prompt that works for one face isn't mistaken for working in general:

| # | Who / photo | Why it's in the set |
|---|---|---|
| 1 | You, front-facing, good light | baseline |
| 2 | Different skin tone than #1 | skin tone must be preserved |
| 3 | Glasses and/or beard | accessories/facial hair often get dropped |
| 4 | Long or distinctive hair | hairstyle drift |
| 5 | Older or younger adult | model tends to "average out" age |
| 6 | Slightly angled face or dim photo | robustness |

## Checklist per generated image
**Scene 1 – planting:** kneeling · in a dug garden row · thatched cottage visible · beans being pressed into soil · cloth pouch · watering can · **no beanstalk yet** · the time of day, mood and outfit you picked.
**Scene 2 – climbing:** gripping vine with both hands · foot on a leaf · looking up · clouds just above · cottage/fields tiny far below.
**Likeness:** face shape · eyes · nose · skin tone · hair color/length/style · glasses/facial hair · apparent age.

## Log
Click **Check likeness and scene** under a generated scene, then **Copy as a test-log row** and paste it below.
Add which test person it was in the Scene column (e.g. "Planting – #3 glasses/beard").

| Date | Scene | Settings | Likeness (score, features) | Scene fidelity | Misses |
|---|---|---|---|---|---|

The AI check is a helper, not the final word: always look at the image yourself too, and note anything it got wrong.

## Changes from classmate feedback (Oct 21)
| Feedback | Change |
|---|---|
| Cartoon didn't look like me; remaking it got worse (Shaul, Reuven) | Default model `gpt-image-1` with high input fidelity; default exaggeration Subtle; new **Fix my cartoon** box revises the current cartoon from your notes instead of starting over |
| Climbing scene: two noses, half a face in the beanstalk, didn't match the cartoon (Shaul) | Scene prompt now requires one head/one face, body in front of the vines, and treats the cartoon as the design source (photo only as a feature reference); climbing pose changed to a side view with the face in three-quarter view |
| Picked 3D animated, got claymation (Yosef) | 3D style rewritten as a glossy CGI render; clay style made distinctly handmade. Wording is positive-only, because naming "clay" can pull results toward it |
| Too many options (Shaul, Reuven) | Only style + glasses (step 1) and mood + outfit (step 2) are shown; the rest is under More options |
| Download/Check buttons visible before a scene existed | Fixed (`[hidden]` was overridden by CSS) |

## Common fixes
- Face too generic / wrong person → set exaggeration to Subtle, use a sharper photo, strengthen `IDENTITY_RULES` with the feature that drifted (e.g. "keep the glasses").
- Face too small in the climbing scene → it's a tall shot; add "Jack's face fills at least a tenth of the frame" to `scene_prompt`.
- Beanstalk appears in scene 1 → keep "No beanstalk has grown yet" in the spec (it's there for this reason).
- Missing prop → name it earlier in the spec; models drop items near the end of long lists.

Keep the caption truthful: if you change what the scene shows, change the text in `build_scene` in app.py — the caption updates automatically.
