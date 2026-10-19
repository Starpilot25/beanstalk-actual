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
**Scene 1 – planting:** kneeling · in a dug garden row · thatched cottage visible · beans being pressed into soil · cloth pouch · watering can · **no beanstalk yet** · morning light.
**Scene 2 – climbing:** gripping vine with both hands · foot on a leaf · looking up · clouds just above · cottage/fields tiny far below.
**Likeness:** face shape · eyes · nose · skin tone · hair color/length/style · glasses/facial hair · apparent age.

## Log
| Upload | Settings | Prompt version | Likeness (cartoon / S1 / S2) | Scene fidelity (S1 / S2) — what was missing | Change made next |
|---|---|---|---|---|---|
| | | v1 | | | |

## Common fixes
- Face too generic / wrong person → set exaggeration to Subtle, use a sharper photo, strengthen `IDENTITY_RULES` with the feature that drifted (e.g. "keep the glasses").
- Face too small in the climbing scene → it's a tall shot; add "Jack's face fills at least a tenth of the frame" to `scene_prompt`.
- Beanstalk appears in scene 1 → keep "No beanstalk has grown yet" in the spec (it's there for this reason).
- Missing prop → name it earlier in the spec; models drop items near the end of long lists.

Keep the caption truthful: if you change what the scene shows, change the `SCENES` text — the caption updates automatically.
