# Bhasha Dub

Indian enterprises (banks, insurers, fintechs, edtechs) record training and explainer videos in English, and dubbing them into regional languages takes weeks. Bhasha Dub turns a short clip into any of 10 Indian languages (plus Hinglish) in **the original speaker's cloned voice**, in under a minute.

**Live demo: https://bhasha-dub.onrender.com** (free tier, so the first load can take ~30 s while it wakes up)

Built for the Gnani.ai Great Indian AI Internship Challenge. #GnaniAI #GreatIndianAIInternshipChallenge

## Pipeline

```
clip (≤20 s) ─ffmpeg─► 16 kHz mono wav
   ├─► Gnani Prisma v3.0 STT (indic-auto)        → transcript + detected language
   ├─► Gnani Voice Clone embeddings              → speaker embedding
   └─► Groq LLM: natural code-mixed translation, keeps KYC/EMI/UPI terms in English
           └─► Gnani vachana-vc-v1 (cloned voice) or Timbre v2.5 (studio voice)
                   └─► ffmpeg atempo duration sync → mux back onto the video
```

Transcripts and voice embeddings are cached per file (SHA-256), so dubbing the same clip into another language, or re-synthesizing an edited line, only calls TTS.

## Stack

- `pipeline.py`: Gnani + Groq calls, caching, ffmpeg sync
- `server.py`: FastAPI; streams each pipeline step to the browser as NDJSON
- `static/`: hand-built frontend (HTML/CSS/JS, no build step)

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GNANI_API_KEY and GROQ_API_KEY
python -m uvicorn server:app --port 8000
```

Open http://localhost:8000. ffmpeg comes bundled through `imageio-ffmpeg`.

## Deploy

`render.yaml` deploys it as one free Render web service; set `GNANI_API_KEY` and `GROQ_API_KEY` in the Render dashboard. A daily cap (`MAX_RUNS_PER_DAY`, default 40) protects API credits on a public link.
