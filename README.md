# Into the Beanstalk — MCON 368

Upload a photo → cartoonify it (style, exaggeration, colors, quality) → place the cartoon you into two Jack and the Beanstalk scenes. Each scene image is captioned with the exact scene specification sent to the model.

**Model:** OpenAI `gpt-image-1-mini` via the image-edit endpoint (about 2¢ for a full run: 1 cartoon + 2 scenes at Draft quality). The original photo is sent with every scene as a face reference. For stronger likeness set `IMAGE_MODEL=gpt-image-1` in Render: it adds `input_fidelity="high"` automatically, but costs roughly 20–30¢ per run. The cost line on the page adjusts to the model in use.

## Features
- Upload, drag-and-drop, or take a photo with the webcam
- Cartoon settings: art style and glasses up front; exaggeration (default Subtle), colors, outlines and quality under **More options**
- **Fix my cartoon**: describe what's off ("my face is thinner") and the current cartoon is revised against the photo, in one API call
- Scene options: Jack's mood and outfit (incl. "my own clothes") up front; time of day and Surprise me under **More options**; optional extra element per scene
- Caption = the full scene specification sent (options are written into it)
- **AI fidelity check**: one click sends the generated scene to a vision model (`CHECK_MODEL`, default `gpt-4.1-mini`), which compares it with the uploaded photo (likeness score + feature checklist) and grades every element of the caption ✓/✗; results copy straight into TESTING.md
- Download each scene, or a combined captioned **storybook page** (built in the browser, no API call)
- Live cost estimate, generation timer, full-screen image viewer, works on phones

## How it meets the rules
- **Key in env var only:** read from `OPENAI_API_KEY`. `.env` is git-ignored; `render.yaml` marks the key `sync: false` so its value lives only in Render's dashboard.
- **No loops around the API call:** every button click makes exactly one API call. The SDK's automatic retries are disabled (`max_retries=0`) since those are a hidden retry loop.
- **Caption = scene spec:** the caption shown is the same string `build_scene()` inserts into the prompt, including the user's scene options.
- **Same person across scenes:** both scene calls send the cartoon *and* the original photo as references.
- Basic guardrails: 40 requests/hour per IP (change with `HOURLY_LIMIT`), uploads resized to ≤1024px, photos never stored.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # Windows: set OPENAI_API_KEY=sk-...
python app.py                       # http://localhost:5000
```

## Deploy to Render
1. Push this folder to a new GitHub repo (check `git status` first — no `.env` should be listed).
2. In Render: **New → Blueprint**, pick the repo (it reads `render.yaml`). Or **New → Web Service** with
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 1 --threads 4 --timeout 180`
3. Under the service's **Environment** tab, add `OPENAI_API_KEY` with your key. Save → it redeploys.
4. Open the `.onrender.com` URL. The free tier sleeps when idle, so the first load can take ~50s.

Also set a monthly spending limit in your OpenAI billing settings — the URL is public.

## Tuning
Prompts live at the top of `app.py`: `SCENES`, `IDENTITY_RULES`, `cartoon_prompt`, `scene_prompt`. Record each change and its effect in `TESTING.md`.
