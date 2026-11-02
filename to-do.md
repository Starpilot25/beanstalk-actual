# To do

What still needs work in this build, most important first.

## Consistency (the book fails without this)
- **Faces haven't been checked across all three pages with several kids yet.** Jack is copied from one
  cast sheet, but `gpt-image-2.5-flare` has no face-fidelity setting, so the face can still drift,
  especially on page 3, where it's dusk and Jack is small in the doorway. Test with at least 5 different
  photos and log results in `PROMPTS.md`.
- **The cow looked different on pages 1 and 2** because only Jack had a reference image. Fixed by turning
  Jack's sheet into a cast sheet (Jack's face close-up + full-body Jack, mother, cow, old man). Still to check:
  whether squeezing four characters onto one sheet makes Jack's full-body view too small to copy his outfit.
- **The required style fights likeness.** "Large expressive eyes" pushes faces toward a generic
  cartoon kid. The hero prompt asks to keep real proportions, but the balance needs more Playground
  testing.

## Pages and text
- **Hands still sometimes have the wrong number of fingers.** Every page now describes correct hands and
  uses simple hand poses, and "Change it" can repair hands on one page, but it isn't guaranteed. Page 2 (the old man's
  open palm) is the riskiest.
- **The number of beans can still be wrong.** The story says five. Pages 2 and 3 now describe the same
  five beans in five named colors (red, yellow, green, blue, purple), which helps a lot, but image models
  still can't count reliably.
- **The text area isn't guaranteed to be calm.** The prompt asks for a quiet lower third / sky / dark grass,
  but nothing checks it. A busy floor or sky makes the words hard to read. Possible fix: measure how busy
  that strip is and warn the user to repaint.
- **Story text always says "Jack" and "his".** The child is always Jack, even if the uploader's child is a girl.
  Decide whether to offer the child's name or other pronouns.
- No cover or title page yet.
- Page 4 (the beanstalk at dawn) isn't built. It's one more entry in `PAGES` in `storyboard.py`.

## Scaling to 20 pages
- **Everything lives in the browser.** Refreshing the page loses Jack and all pages. For 20 pages that's
  ~20 paid images gone. Save them server-side (or in browser storage) per book.
- **The PDF request sends every image at once.** That's ~1–3 MB now; at 20 pages it gets big. Store pages on the server
  and build the PDF from there.
- Each page is one click on purpose (no loops around the API). With 20 pages that's a lot of clicking,
  so I need a design that stays within the rule.

## Cost and limits
- **A book costs about 20¢** (`gpt-image-2.5-flare` at medium: the cast sheet plus 3 pages, ~5¢ each).
  At 20 pages that's about $1 per book. `low` quality was much cheaper but looked smeared and waxy.
- **The usage limits live in memory** (3 books, 5 changes and 20 pictures per person per hour; 20 books per hour
  site-wide), so they reset whenever Render restarts the app, including after every deploy. A small database
  would make them stick.

## Smaller things
- The PDF has no alt text for the pictures.
