# To do

What's still wrong or unproven, most important first. Updated after each review run (see `review-log.md`).

## Speed
- **A book is about 57–58 s when no page needs a full repaint.** Imperfect pages stop being repainted after
  30 s (`RETRY_DEADLINE`) so the book stays under a minute; that means some pages keep their first try even
  though the check found a small problem. Pages that are actually wrong (the child missing, the stand-in
  mannequin left in, a refused picture) still get all 3 tries, and those books can take 75–85 s.
- **The first visit after 15 minutes idle is slow.** Render's free plan puts the server to sleep, and waking it
  takes up to a minute. Once awake, the page loads in about 0.5 s. A paid instance would fix this.
- **OpenAI's image limit is 20 a minute on our tier.** One book uses about 16, so two people starting books in
  the same minute will queue and go over 60 s.

## Reliability
- **Fixed in Run 1:** the server ran out of memory mid-book (16 pages at once, each holding ~3 MB PNGs on a
  512 MB server). Pictures now go to the API as JPEGs.
- **Fixed in Run 2:** a status check could mark a finished book "failed" and refund it, if it read "running" a
  moment before the job finished. A book is now failed only if it's still running in the same database step.
- **The OpenAI key expired once** and every call failed with 401. Books failed and refunded correctly, but
  nothing warns the owner; the admin log is the only place it shows.

## The book
- **Text placement relies on a vision check of a 3x3 grid.** It once called the top of Jack p. 16 clear when the
  giant's head was there. That page now puts its words under the picture, and the check now counts the top of a
  head or hair, but other pages are only as good as that check. Pre-made scenes are worth a look by eye after any
  redraw.
- **Likeness has only been tested on one person's face.** Try other photos: glasses, curly hair, darker and
  lighter skin, a girl and a boy.
- **OpenAI's safety filter refuses some ordinary characters** (Jack's mother, the harp). Their bible portraits
  fall back to `gpt-image-1.5` / `gpt-image-1`, so they can look slightly different from the rest.
- The hero is still called Jack or Red in the story; only the cover and About Me page use the child's name.

## Money
- Asking for a refund and processing it are two clicks by the same person; there's no separate store owner in
  this sandbox.
- A $5 card-refund request from Nov 12 is stuck at "Requested" (made before the fix that ties card refunds to
  their Stripe checkout); processing it fails harmlessly.
- Hourly limits are kept in memory and reset on every deploy.
