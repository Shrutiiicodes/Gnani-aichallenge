# Bhasha Dub

Indian enterprises (banks, insurers, fintechs, edtechs) record training and explainer videos in English, and dubbing them into regional languages takes weeks. Bhasha Dub turns a short clip into any of 10 Indian languages (plus Hinglish) in **the original speaker's cloned voice**, in under a minute.

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

## Run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GNANI_API_KEY and GROQ_API_KEY
streamlit run app.py
```

ffmpeg comes bundled through `imageio-ffmpeg`; no separate install needed.
