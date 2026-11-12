# To do

Known defects and open questions in the 20-page build, most costly first. Updated after every review run
(see `review-log.md`).

## Not measured yet on the live site
- **The 60-second target hasn't been timed with real image calls.** With 1 hero call, 15 page calls and 16
  checks, the floor is roughly: hero (~15–25 s) + slowest page (~15–25 s) + its check (~3–6 s) + PDF (~1 s).
  Repaints only fit if the first tries are fast; after `RETRY_DEADLINE` (48 s) no new repaint starts.
- **The account's images-per-minute limit is 20 on OpenAI's lowest tier.** One book is 16 images on a good run,
  so two books started in the same minute, or a book with several repaints, will queue and miss 60 s.
  Raising the tier (or `IMAGES_PER_MINUTE` once raised) is the only real fix.
- **The analysis model's grid is coarse.** Words go in a band only if the vision check marks all three cells
  of that band empty. If the check misses a face, the words could cover it. The scenes' bands are checked when
  they're drawn, and the hero is placed outside the band by the prompt, but this needs checking page by page
  in real PDFs of both stories.
- **Likeness across 15 pages.** The hero is edited into each scene from one hero sheet. Compare pages 1, 10
  and 20 with several photos (glasses, curly hair, darker and lighter skin, a girl and a boy).

## Book
- **OpenAI's image safety filter refuses some ordinary characters.** gpt-image-2.5-flare refused Jack's mother's
  portrait 10 times (4 descriptions, both moderation levels), and refused scenes that used the golden harp's
  portrait as a reference. Bible portraits now fall back to `gpt-image-1.5`, then `gpt-image-1`
  (`BIBLE_FALLBACK_MODELS`), and a refused scene retries without reference pictures. A portrait from a
  different model may look slightly different from the rest of the bible; every page is still painted by flare.
- **Expressions are now specified and checked for every character on every page** (`FEELINGS` in `stories.py`):
  the hero's feeling per page, and each supporting character's (e.g. the wolf's fake smile and hungry eyes on p. 4,
  his terror fleeing on p. 16). The check fails a bland face where the page calls for menace or fear. The wolf and
  the giant were redesigned as proper storybook villains. Risk: menacing faces are more likely to be refused by the
  image filter; watch the admin log on wolf pages 7, 13 and 14.
- Five pages per story are pre-made scenes without the hero. Check that a reader doesn't feel the hero
  disappears (Jack pp. 7, 10, 13, 16, 19; Red the same).
- The words never use "he" or "she" for the hero (it's always "Jack", "Red" or "Mother"), so they fit a boy or a
  girl. The hero is still called Jack or Red, not the child's own name; the About Me page carries the name.
- No cover page: the PDF opens on page 1. Kept out on purpose so the page count is exactly 20 + About Me.

## Money
- Refund processing is done by the same user who asked for it (there's no separate store owner in this
  sandbox), so "request" and "process" are two clicks by one person.
- Card refunds need the deposit's Stripe checkout session; deposits made before this version can't be refunded
  to the card.

## Limits
- Per-hour limits live in memory and reset on every deploy.
- If the server restarts while a book is being made, the book is marked failed on the next start and the $0.99
  is refunded; the user has to start again.
