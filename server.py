"""Bhasha Dub web server: serves the frontend and streams pipeline steps as NDJSON."""
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import pipeline as P

MAX_UPLOAD = 50 * 1024 * 1024
STATIC = Path(__file__).with_name("static")
P.WORK.mkdir(exist_ok=True)

app = FastAPI(title="Bhasha Dub")
app.mount("/media", StaticFiles(directory=P.WORK), name="media")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def stream(events):
    def gen():
        try:
            for e in events:
                yield json.dumps(e, ensure_ascii=False) + "\n"
        except Exception as e:  # surface API/ffmpeg errors in the UI instead of a dropped connection
            yield json.dumps({"error": str(e)[:500]}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")


def validate(lang, mode, consent):
    if lang not in P.LANGS or mode not in ("clone", "timbre"):
        raise HTTPException(400, "Unknown language or voice mode")
    if mode == "clone" and not consent:
        raise HTTPException(400, "Voice cloning needs the speaker's consent")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
def config():
    return {"languages": list(P.LANGS), "ready": bool(P.KEY and P.GROQ_KEY), "max_seconds": P.MAX_SEC}


@app.post("/api/dub")
async def dub(lang: str = Form(...), mode: str = Form("clone"), keep: bool = Form(True),
              consent: bool = Form(False), sample: bool = Form(False), file: UploadFile | None = File(None)):
    validate(lang, mode, consent)
    if sample:
        data, name = P.SAMPLE.read_bytes(), P.SAMPLE.name
    elif file:
        data, name = await file.read(MAX_UPLOAD + 1), file.filename or "clip.wav"
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "File too large (max 50 MB). Only the first 20 seconds are used anyway.")
        if Path(name).suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv", ".wav", ".mp3", ".m4a", ".ogg"}:
            raise HTTPException(400, "Unsupported file type")
    else:
        raise HTTPException(400, "Upload a clip or use the sample")
    return stream(P.dub(data, name, lang, mode, keep))


class Resynth(BaseModel):
    id: str
    lang: str
    mode: str
    text: str
    consent: bool = False


@app.post("/api/resynth")
def resynth(r: Resynth):
    validate(r.lang, r.mode, r.consent)
    if not r.text.strip() or len(r.text) > 1500:
        raise HTTPException(400, "Text must be 1–1500 characters")
    try:
        job = P.Job(r.id)
        if r.mode == "clone" and "embedding" not in job.cache:
            raise HTTPException(400, "Run the full dub in cloned-voice mode first")
        return job.synth(r.text, r.lang, r.mode)
    except (ValueError, StopIteration):
        raise HTTPException(404, "Unknown clip, please upload again")
    except RuntimeError as e:
        raise HTTPException(502, str(e)[:500])
