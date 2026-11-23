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

## From the feedback (see `FEEDBACK.md`)
- **Accessories drift:** glasses, earrings, a nose stud come and go between pages. Name them in the hero sheet and
  check them on every page.
- **The wolf is too scary for preschoolers** on Red pp. 11–15 (three personas). I made him scarier on purpose; a
  gentler option for younger children is worth considering.
- **Writing:** "BIG TEETH" in capitals on Red p. 13 reads as shouting; the woodcutter's rescue on p. 15 is abrupt.
- **Typography:** words on full-bleed pages sit in a plain band; an illustrator called it "pasted on".
- **Ask real people the full questions:** the form never asked "Does the story ring true?" or "What isn't good?",
  and friends and family are kind. Next time, ask both, and ask strangers.
- Fixed from the feedback: the beans no longer look like jellybeans, and Jack scenes 1 and 20 no longer contain a
  leftover boy (redrawn).

## Money
- Asking for a refund and processing it are two clicks by the same person; there's no separate store owner in
  this sandbox.
- A $5 card-refund request from Nov 12 is stuck at "Requested" (made before the fix that ties card refunds to
  their Stripe checkout); processing it fails harmlessly.
- Hourly limits are kept in memory and reset on every deploy.

## Printing (added in Run 2)
- **Lulu sandbox only.** Orders stop at "Unpaid": the sandbox never prints. Real printing needs a production Lulu
  account with a card on file, and that's a real charge per book.
- **Print resolution:** the art is 1536 px wide spread over 11 in (about 140 PPI). Lulu recommends 300. Upscale or
  paint larger before a real print run.
- **US addresses only**, and no emails when Lulu's status changes; the customer has to look at "My printed orders".
- **Reprints aren't handled:** a damaged or disliked book would be reprinted at our cost (~$21), which wipes out the
  margin on two and a half books.
- **Name checks need OpenAI.** If it's down, books are refused ("try again") rather than made unchecked.
- **One server worker:** gunicorn runs 1 worker with 4 threads on 512 MB. A restart (as in Run 2, book #48) loses
  the book in progress; the charge is refunded automatically.
