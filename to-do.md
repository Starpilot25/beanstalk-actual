# To do

What still needs work in this build, most important first.

## Consistency (the book fails without this)
- **Faces haven't been checked across all three pages with several kids yet.** Jack is drawn from one
  reference image, but `gpt-image-1-mini` doesn't support high input fidelity, so the face can drift,
  especially on page 3, where it's dusk and Jack is smaller in the doorway. Test with at least 5 different
  photos and log results in `PROMPTS.md`.
- **Only Jack has a reference image.** The mother (pages 1 and 3) and Milky-White (pages 1 and 2) are
  held together by text descriptions alone, so they may not match between pages.
- **The required style fights likeness.** "Large expressive eyes" pushes faces toward a generic
  cartoon kid. The hero prompt asks to keep real proportions, but the balance needs more Playground
  testing.

## Pages and text
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

## Smaller things
- The rate limit is kept in memory, so it resets whenever Render restarts the app.
- The PDF has no alt text for the pictures.
- Draft quality (`low`) keeps costs at about 1¢ per image, but the art is softer. Compare with `medium`.
