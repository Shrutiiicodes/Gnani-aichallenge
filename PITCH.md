# Bhasha Dub: one training video, every Indian language, the trainer's own voice

**Live:** https://bhasha-dub.onrender.com · **Code:** https://github.com/Shrutiiicodes/Gnani-aichallenge · **Built on:** Gnani Prisma v3, Voice Clone v1, Timbre v2.5

## Problem
Indian banks, NBFCs, insurers and edtechs produce thousands of training, onboarding and customer-explainer videos, almost all in English. Their frontline staff and customers learn best in Kannada, Tamil, Marathi or Hindi. Localizing one video today means translators, voice artists and a studio: it takes weeks, costs lakhs across a library, and the new voice never sounds like the original trainer.

## Solution
Bhasha Dub takes a short video or audio clip and returns it dubbed into any of 10 Indian languages (plus Hinglish) **in the original speaker's cloned voice**, in under a minute.

1. **Gnani Prisma v3** transcribes the clip with automatic language detection (handles Hinglish/code-mixed speech).
2. **Gnani Voice Clone** builds a speaker embedding from a few seconds of the original audio.
3. **An LLM adapts the script** the way people actually speak, not textbook translation, keeping domain terms like KYC, EMI and UPI in English and matching the original's length.
4. **Gnani voice-clone TTS** (or a **Timbre** studio voice) speaks the new script; ffmpeg time-matches it and muxes it back onto the video.
5. The user can **edit any word and re-synthesize** in seconds.

## Why it matters for Gnani's customers
- Gnani already serves BFSI, insurance and contact-centre clients; every one of them has a training/explainer library that needs vernacular versions.
- Voice consistency builds trust: customers hear the same familiar trainer or brand voice in their own language.
- It is a showcase of Gnani's full voice stack (STT, voice cloning, TTS) working together in one product.

## Built to be practical
- **Cost-aware:** transcripts and voice embeddings are cached per file, so each extra language costs a single TTS call; clips are capped at 20 s for the demo.
- **Responsible:** cloning requires explicit consent; Timbre preset voices are the no-clone alternative; a daily cap protects API credits on the public link.
- **Simple stack:** FastAPI + a no-build HTML/JS frontend, deployed as one service. Each pipeline step streams live to the UI.

## What's next
Lip sync for on-camera speakers · chunked processing for full-length videos · batch dubbing of an entire training library into every language · subtitle (SRT) export · Evon for on-prem translation.

**Team:** Shruti Deshpande (solo), SVKM's Dwarkadas J. Sanghvi College of Engineering
