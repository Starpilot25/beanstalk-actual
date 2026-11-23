# Feedback: 10 real people, 10 AI personas

Both groups were asked the same thing about their book: **Does this look like me? Does the story ring true? Does it
look professional? What isn't good?**

- **Real responses:** [`feedback/real-responses.md`](feedback/real-responses.md). These are 10 friends and family
  members, none of them developers, aged 18 to 87, using phones, a tablet and computers. Five answered a Google Form
  ([export](feedback/real-responses-form.csv)) and five answered in person.
- **AI responses:** [`personas/out/responses.md`](personas/out/responses.md), with each persona's photo, pages and
  answers. The raw answers are in [`personas/out/responses.csv`](personas/out/responses.csv).

## How the AI personas were made different

`personas/run_personas.py` makes 10 personas that differ along the axes that change what someone notices:

- **Who they are.** Their ages run from 19 to 71. The group includes parents, a grandparent, a retired teacher, a
  professional illustrator, a UX designer, an engineer, and people without children.
- **Their face**, which is what really tests the app: glasses, a full white beard, a hijab, gray hair, freckles,
  teal curly hair, a shaved head, and a range of skin tones.
- **Their story and their history with it.** Five made Jack and the Beanstalk and five made Little Red Riding Hood.
  One persona didn't grow up with the story at all.
- **Their bar and their voice.** Some are generous, some are harsh experts, and one is an impatient student who
  writes in lowercase. One writes English as a second language.

Each persona reviews **its own book**. A photo of the persona is generated, and the app's real pipeline makes their
full 20-page book from that photo. Then a vision model, playing the persona, sees the photo and every page with its
words, and answers the survey. To keep the cost down (about $3 for all ten), the pictures were made at low quality
and imperfect pages weren't repainted.

## Scores

| | Looks like me | Rings true | Professional |
|---|---|---|---|
| **Real people** (yes/no) | 9 of 10 yes | not asked | 10 of 10 "looks great" |
| **AI personas** (1–5) | 3.5 avg (range 3–4) | 4.5 avg (range 3–5) | 4.4 avg (range 3–5) |

The two groups agree on the headline: the books look polished and like the person, but not perfectly so.

## What people caught that the AI didn't

- **Whether it actually looks like *them*.** One real person said the hero didn't really look like them. An AI
  persona is judging a face it has only ever seen in one generated photo. A real person knows their own face and so
  do the people around them, which is the test that matters for a gift. All ten AI personas hedged in the 3–4 range.
  None of them could give a real "no" or a real "anyone would recognize me".
- **That it works for the people who will use it.** An 87-year-old on a tablet and a 74-year-old on a phone both
  got through it without trouble ("Nothing" went wrong). The AI personas were told sign-in and painting worked, so
  they couldn't test usability at all.
- **The emotional reaction.** "It's a very cute illustration." Every real answer was simply pleased. That's
  partly politeness from friends and family, but it's also what a gift buyer actually feels.

## What the AI caught that people didn't

None of the real answers named a specific flaw. The AI personas named page-level problems, and I checked them
against the pictures:

| Problem the AI reported | Who said it | Checked | Action |
|---|---|---|---|
| The magic beans look like candy or jellybeans (Jack pp. 5–6) | all 5 Jack personas | **Real.** They're bright primary colors. | Bean description changed to earthy, speckled real beans with a faint glow; the scenes are being redrawn |
| An extra boy in Jack's final family picture (p. 20); a young boy instead of the hero on p. 1 of one book | Marcus, Sam, Hank | **Real.** The shared Jack scenes 1 and 20 contain a boy instead of the faceless stand-in, so the hero swap sometimes leaves him in | Redraw Jack scenes 1 and 20 |
| The hero's age and details drift: glasses, earrings and the nose stud come and go, and the face is sometimes childlike | 9 of 10 | **Real, partly by design**: the hero is drawn at a child's proportions. Missing accessories are a real likeness gap | Into `to-do.md`: name the accessories in the hero sheet and check them on every page |
| The wolf is too frightening for preschoolers (Red pp. 11–15) | Amira, Lupe, Grace | A fair tradeoff: I made the wolf scarier on purpose earlier | Noted; not changed |
| "BIG TEETH" in capitals is jarring (Red p. 13); the woodcutter's rescue is abrupt (p. 15) | Amira, Grace, Priya | Real writing notes | Into `to-do.md` |
| Text is "pasted on", with no typographic design | Priya (illustrator) | Partly. Framed pages put the words on paper, but full-bleed pages use a plain band | Into `to-do.md` |
| **"Two Reds standing together" on Red p. 6** | Denise | **False.** There's one Red and the wolf | The AI can invent defects, so every claim needed checking |

## What the comparison taught me

1. **The AI is a better defect finder, and real people are better judges of the thing that matters.** The AI listed
   specific page problems that ten real people never mentioned. Only real people can say "that's not me".
2. **The AI personas weren't as different as their voices.** They wrote very differently (lowercase student,
   blunt illustrator, ESL baker), but they converged on the same findings: jellybeans, stylized faces, detail
   drift. Different voices aren't the same as different perspectives. The only findings unique to one persona
   came from personas with a specific expertise (Priya on hands and typography, Grace on reading level), so
   that's the axis worth spreading further.
3. **AI feedback needs checking.** One persona invented a "second Red". With 10 personas, a claim that only one of
   them makes deserves suspicion; a claim all five make (the beans) is almost certainly real.
4. **The real survey asked too little.** The form never asked "Does the story ring true?" or "What isn't good?",
   so the real group couldn't give the specific criticism the AI did. Next time, ask both questions, and ask
   people outside friends and family.
