# Review log

Every run of the `storybook-review` skill against the live site, oldest first. Entries are only ever appended,
never edited or deleted.

---

## Run 1 — Mon Nov 16 2026, 3:37–4:25 pm ET (20:37–21:25 UTC)

**Reviewer:** Claude, driving the Claude desktop app's built-in browser (Chromium) against https://beanstalk.autosignusa.com,
signed in as the site owner. Funding, sign-out and sign-in were done by the owner in the same browser (the reviewer
doesn't type card numbers or passwords).
**Photo:** `WIN_20231002_13_18_28_Pro.jpg`, cropped to the face (360×470), not one of the development test photos.
Caveat: it is very probably the same person as the developer's own photos, so likeness is tested on a familiar face.
**Name/age/likes used:** Sam, 7, "dinosaurs and climbing trees".
**Commits live during the run:** start = `4266242`; mid-run fixes `7de7255` (JPEG inputs), "Build the PDF without
re-encoding pictures", `6773d33` (binary PDF images, `/version`). The refund fix below was written after the run and
is not yet live.

### Clocks (submit click → PDF ready, from the browser)

| Book | Story | Code | Submitted (UTC) | PDF ready (UTC) | Total | Hero sheet | Pages done | PDF step | Result |
|---|---|---|---|---|---|---|---|---|---|
| #40 | Jack | 4266242 | 20:40:28 | 20:42:39 | **131 s** | 16 s | 108 s | 21 s | done, 22 pages |
| #41 | Red | 4266242 | 20:43:26 | — | — | — | — | — | **failed at 147 s: server restarted** (out of memory, most likely); $0.99 refunded automatically |
| #42 | Red | 7de7255 | 20:59:06 | 21:00:20 | **74 s** | 16 s | 55 s | 18 s | done |
| #43 | Jack | PDF re-encode fix | 21:08:10 | 21:09:36 | **86 s** | 15 s | 70 s (1 repaint) | 16 s | done |
| #44 | Red | 6773d33 | 21:17:09 | 21:18:30 | **81 s** | 17 s | 75 s (1 repaint) | 2.5 s | done — **PDF reviewed** |
| #45 | Jack | 6773d33 | 21:18:57 | 21:19:54 | **57 s** | 13 s | 54 s | 2.4 s | done — **PDF reviewed** |

PDF step on 6773d33: load 0.3–0.5 s, build 0.4 s, save 1.5–1.8 s. No rate-limit waits on any book.

### Balance trail

$0.00 (after the earlier $4.06 card refund `re_3Ub31xD77uFrOgI50mxYt9UK`) → book refused at $0.00 with "A book costs $0.99
and your balance is $0.00. Add funds" → owner added $5.00 with the Stripe test card (credited at once) → $4.01 (#40)
→ $3.02 (#41) → $4.01 (#41 auto-refund) → $3.02 (#42) → $2.03 (#43) → $1.04 (#44) → **$0.05** (#45).
The wallet's own check: "the 19 rows add up to $0.05, which matches your balance of $0.05".

### Cost

Wallet: **$0.84 average API cost per book** over 7 finished books vs **$0.99** charged (+$0.15). Per book: pages
(first try) $0.76, repaints $0.048, hero $0.017, analysis checks $0.012; 35.6 calls. Shared art (bible + scenes,
once for all books): 362 calls, $5.10. Average time over all finished books 102 s, fastest 55 s.

### Scores

| Section | Score | Evidence |
|---|---|---|
| Money: fund, balance, $0.99, history, refunds, API cost log | **8/10** | Refused at $0.00 with Add funds; Stripe test deposit credited; every charge and refund in the history, which reconciles; card refund processed earlier via Stripe; cost per book shown beside $0.99. **Defect:** a failed book's charge (#41, and #1) still offered "Request refund" after the automatic refund, so it could be refunded twice. Old $5 card-refund request from Nov 12 still sits at "Requested". |
| The book: 20-page template + About Me, both stories, bible, pre-made scenes | **8/10** | Both PDFs: cover + 20 pages + About Me = 22 pages, same layout for both stories. Hero in costume on every hero page; Red in a skirt throughout; adults adult-sized; wolf menacing. **Defect:** Milky-White has brown patches on Jack pp. 3–4 but is pure white on pp. 1 and 20 (the bible says no spots). |
| Speed: page load, images + PDF < 60 s, named stages, thumbnails | **6/10** | Page load 0.5 s (measured earlier, TTFB 0.28 s). Progress bar names each stage ("Drawing Sam as Jack", "Painting and checking pages: n of 21 done, repainting 1", "Putting the book together"); thumbnails appear per page with try counts. **Only 1 of 4 books on final code under 60 s** (57 s); any page that needs a repaint pushes the book to 75–86 s. |
| Persistence across sign-ins | **10/10** | After the owner signed out and back in, "My books" listed every book with its time, and both PDFs (#44, #45) downloaded again (200, ~5.5 MB each). |
| Quality loop: analyse every image, up to 3, best kept, attempts visible | **9/10** | Every tile shows "try n/3" and a Passed / Best of badge; repaints visible in the stage text; hero sheet analysed (passed first try on every book). |
| Text placement: never over faces or important things | **7/10** | 40 of 42 story pages fine: framed pages put words on the paper; full-bleed pages use clear sky/floor. **Defect:** Jack p. 16, the second line ("harp. The giant woke…") runs across the top of the giant's head. Red p. 10 is close (just above the nightcap) but clear. |
| UI: cleaner | **8/10** | Night-sky header with light cards; at 400 px wide no sideways scroll and everything usable. Step labels ("Pick a story" etc.) are low-contrast grey on the dark sky. |
| Reliability (found by this run) | **4/10 → fixed** | Book #41 killed the server mid-book (16 pages in parallel each holding ~3 MB PNG inputs on a 512 MB instance). Fixed in 7de7255 by sending JPEG inputs; 4 books since without a failure. |

**Total: 60/80 (75%).**

### Not measured

Card refund in this run (done once just before it); Google sign-in from a fresh account; the hand-in links in a
private window (the repo returned 404 to a signed-out browser, so it is private or misnamed right now); other
browsers; more than one user at once.

### Fix first

1. **Speed with repaints:** a repaint after ~45 s lands the book at 75–86 s. Options: a shorter repaint deadline
   (e.g. 35 s), start pages while the hero sheet is still being checked, or lower page quality.
2. **Refund twice on failed books:** written (`billing.refundable` now returns 0 when `reversal-<book>` exists);
   needs pushing and a check that #41 no longer offers "Request refund".
3. **Text over the giant's head (Jack p. 16):** the pre-made scene's analysis called the top band clear. Re-check
   that scene, or fall back to the framed layout when a full-bleed band's top row is marked busy anywhere.
4. Milky-White spots on Jack scenes 3–4: redo those two scenes.
5. Make the GitHub repo public before hand-in.

## Run 2 — Mon Nov 23 2026 ("Print it and ship it")

**Reviewer:** Claude, driving the Claude desktop app's built-in browser against https://beanstalk.autosignusa.com,
signed in as the site owner. Funding and sign-in were done by the owner (the reviewer doesn't type card numbers or
passwords). Lulu is the sandbox (`api.sandbox.lulu.com`); no real book was printed, shipped or paid for.
**Name/age/likes used:** Sam, 7, "dinosaurs and pancakes"; About Me "wants to be a paleontologist".

### Clocks (submit click → PDF ready)

| Book | Story | Total | Result |
|---|---|---|---|
| #46 | Red | **58 s** | done, but a status check marked it "failed" a moment after it finished and refunded it. Fixed (`fail_if_running`: a book is failed only if it is still running in the same database step). |
| #47 | Jack | **68 s** | done — **PDF reviewed** (still had jellybean-looking beans) |
| #48 | Red | — | **failed: server restarted.** Most likely caused by the reviewer polling the site every second, which Cloudflare rate-limited (429) while the book ran. Charge refunded automatically. Reviewer switched to the page's own polling. |
| #49 | Red | **72 s** (1 repaint) | done — **PDF reviewed** |
| #50 | Jack | **≈61 s** | done after redrawing Jack scenes 5–6 — **PDF reviewed**, beans now plain brown beans |

### The printed book (Lulu sandbox)

- Product: 11 × 8.5 in landscape, full-colour hardcover (`1100X0850FCSTDCW080CW444GXX`), 24 inside pages. Checked in
  the sandbox: no stapled book at this size; paperback needs 32+ pages; GROUND shipping refused for this product.
- Proof: 26 pages (front cover, 24 inside, back cover), drawn by the same code as the print files. The order button
  is refused by the server until "I've looked at every page" is ticked.
- **Order #1:** refused by Lulu ("pod_package_id: This field is required"; it was in the wrong field). The charge was
  reversed automatically. Fixed.
- **Order #2: Lulu print job 368721** → *Created* → *Unpaid*. Lulu downloaded and accepted both files (interior and
  1728 × 738 pt cover from Lulu's cover-dimensions API). Unpaid is where a sandbox job stops.
- Quotes to New York: standard mail $28.99, expedited $44.99, express $61.99 (Lulu total + $8, rounded up to $x.99).

### The PDFs (#47, #49, #50)

All 23 pages: cover with the title and "starring Sam"; copyright page ("© 2026 Beanstalk Books… Published by
Beanstalk Books, New York, NY", first edition, book number); story pages 1–20 starting on the next page; About Me back
page with the portrait, age, likes and "paleontologist". Jack p. 16's words now sit under the picture, clear of the
giant. Milky-White has no spots on pp. 1–4 and 20.

### Name and About Me checks (live)

Accepted: Sarah, Nkechi, Mary-Kate, Sam. Refused: Stinky, Dummy, Poopface (insults), Hitler (notorious person),
asdfgh (not a name), an About Me with a street address and phone number, and "punching his stupid sister" (moderation).
Checks run while typing, before any charge, and again when a print copy is ordered; if they can't run, the book is
refused rather than made unchecked.

### Scores

| Section | Score | Evidence |
|---|---|---|
| Print API: proof, approval, address, price, order, status | **9/10** | Order #2 accepted by Lulu with our files; approval enforced on the server; signed price; failed order reversed. Sandbox stops at Unpaid, so printing itself is unproven. US addresses only. |
| Looks like a real book | **9/10** | Cover "starring", copyright page with publisher, story on the next page, About Me on the back, in both the PDF and the print files. Print art is the 1536 px picture spread across 11 in (about 140 PPI): fine on screen, soft in print. |
| Name / About Me checks | **9/10** | Every test above gave the right answer. Depends on OpenAI being up (fails closed). |
| Pricing write-up | **9/10** | `WRITEUP.md`: cost per book from the app's own log + Lulu quotes; $8.53 margin (28%) on standard mail, ~$7.36 after card fees. |
| Money (carried over) | **9/10** | Any-amount top-up added; print charges and reversals in the history; failed-book double refund fixed. |
| Speed (carried over) | **7/10** | 58, 61, 68, 72 s: half under 60 s; a repaint still pushes a book over. First visit after idle is slow (free plan). |
| Text placement / pictures | **9/10** | Run 1 defects fixed (giant's head, cow spots, beans, stray boy). |
| UI | **9/10** | New design: night sky, castle and beanstalk, books as paper pages, shelf of covers; checked at 390 px with no sideways scroll. |

**Total: 70/80 (88%)**, up from 60/80.

### Fix first

1. **Speed with repaints:** still 61–72 s when a page needs a repaint.
2. **Print resolution:** upscale the page art (or paint at a larger size) before sending to Lulu.
3. **One-worker server:** a book and heavy traffic share one gunicorn worker on 512 MB; a restart kills a book in
   progress (#48). Refunds are automatic, but the book is lost.
4. Ship outside the US; tell the customer when Lulu's status changes.
