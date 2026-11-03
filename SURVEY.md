# User survey: Jack and the Beanstalk, starring you

The same questions go to 10 real people (CloudResearch Connect) and 10 AI personas (`personas/run_personas.py`),
so the two sets can be compared answer by answer. Results and the comparison are in `FEEDBACK.md`.

---

## 1. Study listing (paste into CloudResearch Connect)

**Title:** Try a picture-book app that turns your photo into a storybook character (10 min)

**Description:**
> You'll use a small web app that turns one photo of you into "Jack" in *Jack and the Beanstalk*, then paints
> the first three pages of the story. After that you'll answer 4 short questions about how it turned out.
> You need a Google account (or the sign-in code in the instructions) and a clear photo of your face.
> Your photo is sent to OpenAI to make the pictures and is not stored. Takes about 10 minutes, mostly waiting
> for the pictures to paint.

- Estimated time: 10 minutes
- Devices: desktop or phone (both work)
- Pay: set it so it comes to at least the platform's recommended hourly rate for 10 minutes
- Participants: 10, US, 18+

---

## 2. Instructions (top of the form)

1. Open **https://beanstalk.autosignusa.com** and sign in with Google.
2. Under **Who is Jack?**, add a clear photo of **your own face** (looking at the camera, good light).
   Type your first name (or a nickname) and, if you like, a few things you love.
3. Click **Create Jack and the cast** and wait about a minute.
4. Click **Paint all 3 pages** and wait about a minute.
5. Flip through your book in step 3. You can download the PDF if you want a copy.
6. Come back here and answer the questions. When you're done, you can delete your book with
   **Delete this book**.

Please only upload a photo of yourself.

---

## 3. Questions (Google Form, all required unless noted)

**About you**
1. Your age range: 18–24 / 25–34 / 35–44 / 45–54 / 55–64 / 65+
2. Do you have children? Yes, under 10 / Yes, 10 or older / No
3. What did you use? Phone / Tablet / Computer
4. Did everything work (sign-in, cast sheet, 3 pages)? Yes / No: if no, what went wrong? *(short answer)*

**The four questions**

5. **Does Jack look like you?** 1 (not at all) – 5 (anyone would recognize me)
6. Why that score? What's right or off about the face? *(paragraph)*
7. **Does the story ring true?** Do the pages feel like *Jack and the Beanstalk*, and like a real children's book?
   1 (not at all) – 5 (completely)
8. Why that score? *(paragraph)*
9. **Does it look professional?** Would you print it, gift it, or pay for it? 1 (looks like a cheap AI demo) –
   5 (looks like a real published book)
10. Why that score? *(paragraph)*
11. **What isn't good?** Anything that bugged you: the pictures, the words, the website, waiting, anything.
    *(paragraph)*
12. *(optional)* Anything you liked?

**For CloudResearch:** last screen shows the completion code.

---

## 4. Before launching

- [ ] On Render, `IMAGE_MODEL` is **not** `fake` (delete the variable or set it to `gpt-image-2.5-flare`).
- [ ] Make a book yourself on the live site in a private window, start to finish.
- [ ] Cost check: about 4 pictures per tester (≈20¢), so 10 testers ≈ $2. The per-person cap is 20 pictures an hour.
- [ ] Form → Responses → link to Sheets, then share the sheet "Anyone with the link can view" (that's the public
      link for the hand-in). Remove any column that could identify someone before sharing.
