# Print it and ship it: what I did

Live site: https://beanstalk.autosignusa.com · everything runs in test mode (Stripe test card, Lulu's sandbox).

## 1. A print API that takes the PDF, prints it and ships it

**Lulu Print API, sandbox** (`lulu.py`). Lulu prints on demand, ships to an address, and has a full sandbox
(`api.sandbox.lulu.com`): orders are accepted, validated and tracked, but never printed, shipped or charged.

The flow on a finished book ("Order a printed copy"):

1. **Review and approve.** The customer opens the *print proof*: the exact book that will be printed, page by
   page at its printed size (front cover, 24 inside pages, back cover), drawn by the same code as the files sent to
   Lulu. They must tick "I've looked at every page and it's ready to print"; the server refuses an order without
   it, so nothing is sent before approval.
2. **Address.** US addresses for now; the name, street, city, two-letter state, 5-digit ZIP and a phone number are
   checked before Lulu is asked.
3. **Price.** Lulu's cost-calculation API prices that address and shipping speed; the page shows printing,
   shipping, handling, tax, our margin and the total. The price is signed by the server, so it can't be edited in
   the browser.
4. **Order.** The price is taken from the balance, the two print files are built and stored, and the app creates a
   Lulu print job whose files Lulu downloads from secret, unguessable links on our site. If Lulu refuses, the
   charge is put straight back. "My printed orders" shows each order and Lulu's live status.

First real sandbox order: **order #2, Lulu print job 368721**, went from *Created* to *Unpaid*. Lulu downloaded and
accepted both files and is waiting for payment, which never comes in the sandbox. (Order #1 was refused because I
had put the product id in the wrong field; it was refunded automatically and the fix is in.)

**Product:** 11 × 8.5 in landscape, full colour, standard-quality **hardcover** (`1100X0850FCSTDCW080CW444GXX`).
I tested the options in the sandbox: Lulu has no stapled book at this size, a paperback needs 32+ pages, and a
hardcover takes our 24, which is what a picture book is anyway.

## 2. It looks like a real book

| | Where |
|---|---|
| Front cover: "Little Red Riding Hood, starring Sam" | the cover art with the title and "starring *name*" |
| Copyright page with the publisher | "Text and illustrations copyright © 2026 Beanstalk Books. All rights reserved…", "Published by Beanstalk Books, New York, NY", what the book is, first edition, book number |
| The story starts after the copyright page | PDF: cover, copyright, pages 1-20. Printed book: title page, copyright page, pages 1-20, The End, padded to 24 |
| Back cover: About Me | the hero portrait, name, age, things they love, and the "all about them" text |

The printed files follow Lulu's rules: 1/8 in bleed on every inside page, every word at least ½ in inside the trim,
and the cover is one flat sheet sized by Lulu's cover-dimensions API (1728 × 738 pt). It has the back cover, an
18 pt spine and the front cover, with the wrap that folds around the boards kept clear of anything that must be
read. Rather than crop the 3:2 art to the 11 × 8.5 page, and risk cutting a face at the edge, each inside page sits
on cream paper with the art bleeding off the sides.

## 3. Checking what the child's grown-up types (`checks.py`)

The name goes on the cover and the details go on the back, so they're checked before anything is made or charged.
The page checks them while they're typed, so the answer is ready before the photo is uploaded and costs the book's
60-second clock nothing.

1. **Rules:** a name is 1-3 words of letters in any alphabet, plus hyphens, apostrophes and periods, 2-30
   characters, with no digits or "aaaa".
2. **OpenAI's moderation model** (free) on everything typed: anything flagged is refused.
3. **A small language-model check** for what moderation lets through. It refuses a name that's really an insult,
   epithet or mean nickname ("Stinky", "Dummy") or not a name at all, and About Me text that doesn't belong in a
   child's book, including private details like a street address, phone number or school.

Tested on the live site (Nov 23):

| Typed | Result |
|---|---|
| Sarah · Nkechi · Mary-Kate | accepted |
| Stinky · Dummy · Poopface | refused: an insult or joke nickname, not a real name |
| Hitler | refused: a notorious real person |
| asdfgh | refused: random letters, not a name |
| About Me: "Lives at 12 Oak Street… call 201-555-…" | refused: a street address and phone number |
| Likes: "punching his stupid sister" | refused by the moderation model |
| Sam, "Dinosaurs and pancakes", "Fastest runner in first grade" | accepted |

If the checks can't run, the book is refused with "try again" rather than printed unchecked. The checks run again
when a printed copy is ordered.

## 4. Price: the business model and the math

Two products: the **digital book for $0.99**, an impulse buy and a preview, and a **printed hardcover shipped to
the door**, priced at Lulu's full cost plus an $8.00 margin, rounded up to $x.99. A printed copy is ordered from a
finished digital book, so every printed book has already paid its $0.99.

**Cost per book** (generation from the app's own log of every API call, averaged over 9 books; printing and
shipping from Lulu's sandbox quotes for a hardcover to New York):

| | Standard mail | Expedited | Express |
|---|---|---|---|
| Generation: 16 pages, hero sheet, ~18 checks, ~1 repaint (OpenAI) | $0.84 | $0.84 | $0.84 |
| Printing, 24-page hardcover (Lulu) | $12.50 | $12.50 | $12.50 |
| Shipping (Lulu) | $5.69 | $20.74 | $35.74 |
| Handling (Lulu) | $0.75 | $0.75 | $0.75 |
| Sales tax (Lulu charges it on its part) | $1.67 | $3.00 | $4.33 |
| **Total cost** | **$21.45** | **$37.83** | **$54.16** |
| **Customer pays** ($0.99 digital + printed price) | $0.99 + $28.99 = **$29.98** | $0.99 + $44.99 = **$45.98** | $0.99 + $61.99 = **$62.98** |
| **Margin** | **$8.53 (28%)** | **$8.15 (18%)** | **$8.82 (14%)** |

The printed price is `Lulu total + $8.00`, rounded up to $x.99: standard is $20.61 + $8.00 = $28.61, so **$28.99**.

What the margin still has to cover, which isn't in the sandbox:

- **Card fees.** Stripe charges about 2.9% + $0.30 per top-up, so about $1.17 on a $30 top-up. That leaves about
  **$7.36** on a standard-mail book.
- **Reprints.** A book that arrives damaged or with a page someone hates is reprinted at our cost, about $21.
  One reprint wipes out the margin on about two and a half books, so the quality checks matter for money too.
- **The shared art** (character bible and pre-made scenes): $5.31 so far, once, for every book.

**Why a flat margin and not a percentage:** shipping is most of the difference between the speeds. A percentage
would make express shipping much more profitable than standard for the same book. A flat $8 keeps the cheapest
way to get the book also the best deal, and it's the one most people choose.

## 5. Carried over from "Charge for the book"

Wallet and Stripe test payments, with a new any-amount top-up so one checkout covers a printed copy. Refunds,
transaction history, and cost per book against the price. Books and PDFs saved across sign-ins. The quality loop
with attempt counts. Text placed clear of faces. Progress by stage, with thumbnails. The review is rerun and
appended to `review-log.md`.

Also new: the site's design (night sky, castle, beanstalk; the finished books as the hero; steps on paper pages)
and the name **Beanstalk Books**, matching the publisher on the copyright page.
