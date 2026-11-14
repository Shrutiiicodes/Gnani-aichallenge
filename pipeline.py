"""Bhasha Dub pipeline: dub a short clip into Indian languages in the speaker's own voice (Gnani Prisma + Voice Clone + Timbre, Groq for translation)."""
import hashlib, json, os, re, subprocess, time, wave
from pathlib import Path

import imageio_ffmpeg
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
GNANI = "https://api.vachana.ai"
KEY = os.getenv("GNANI_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FF = imageio_ffmpeg.get_ffmpeg_exe()
WORK = Path(__file__).with_name("work")
MAX_SEC = 20  # credit guardrail; also under Prisma's 30s REST limit
MAX_RUNS_PER_DAY = int(os.getenv("MAX_RUNS_PER_DAY", "40"))
SAMPLE = Path(__file__).with_name("samples") / "kyc_explainer_en.wav"

# label -> (code, Timbre v2.5 voice)
LANGS = {
    "Hindi": ("hi-IN", "Nalini"), "Kannada": ("kn-IN", "Saanvi"), "Tamil": ("ta-IN", "Asmita"),
    "Telugu": ("te-IN", "Suhana"), "Marathi": ("mr-IN", "Zahira"), "Bengali": ("bn-IN", "Kirra"),
    "Gujarati": ("gu-IN", "Falak"), "Malayalam": ("ml-IN", "Reshma"), "Punjabi": ("pa-IN", "Mehuli"),
    "Hinglish": ("hi-en", "Poorvi"), "English": ("en-IN", "Kaveri"),
}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
AUDIO_CFG = {"sample_rate": 44100, "num_channels": 1, "sample_width": 2, "encoding": "linear_pcm", "container": "wav"}


def ff(*args):
    r = subprocess.run([FF, "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-500:]}")


def wav_seconds(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def check(r):
    if not r.ok:
        raise RuntimeError(f"{r.request.url} -> HTTP {r.status_code}: {r.text[:400]}")
    return r


def gnani_post(path, **kw):
    # Gnani allows one active request per key; retry once on 429.
    for attempt in range(3):
        r = requests.post(GNANI + path, headers={"X-API-Key-ID": KEY}, timeout=120, **kw)
        if r.status_code != 429:
            return check(r)
        time.sleep(2 * (attempt + 1))
    return check(r)


def stt(wav):
    with open(wav, "rb") as f:
        j = gnani_post("/stt/v3", files={"audio_file": ("src.wav", f, "audio/wav")},
                       data={"model": "prisma-v3.0", "language_code": "indic-auto", "format": "transcribe"}).json()
    return j["transcript"], j.get("detected_language_code", "?")


def clone_embedding(wav):
    with open(wav, "rb") as f:
        j = gnani_post("/api/v1/tts/voice-clone/embeddings", files={"audio_file": ("ref.wav", f, "audio/wav")}).json()
    # Docs disagree on the shape: flat {embedding, shape, dtype} vs {data: {voice_clone_embedding: {...}}}.
    emb = (j.get("data") or {}).get("voice_clone_embedding") or j.get("speaker_embedding") or j.get("voice_clone_embedding") or j
    if "embedding" not in emb:
        raise RuntimeError(f"Unexpected embedding response: {str(j)[:300]}")
    return {k: emb[k] for k in ("embedding", "shape", "dtype")}


def tts(text, lang, voice_mode, emb, out):
    code, voice = LANGS[lang]
    if voice_mode == "clone":
        body = {"text": text, "model": "vachana-vc-v1", "speaker_embedding": emb, "audio_config": AUDIO_CFG}
    else:
        body = {"text": text, "model": "timbre-v2.5", "voice": voice, "language": code, "speed": 1.0, "audio_config": AUDIO_CFG}
    # Gnani returns a streaming-style WAV header (bogus length); rewrite it through ffmpeg so durations are correct.
    tmp = out.with_suffix(".tmp.wav")
    tmp.write_bytes(gnani_post("/api/v1/tts/inference", json=body).content)
    ff("-i", str(tmp), str(out))
    tmp.unlink()


def translate(text, lang, seconds, keep_terms):
    script = "Romanized Hindi-English mix (Latin letters)" if lang == "Hinglish" else f"{lang} in its native script"
    terms = ("Keep English technical, banking and product terms (KYC, EMI, UPI, loan, app, insurance, mutual fund, etc.) "
             "as English words, written phonetically in the target script so a TTS voice pronounces them in English. "
             if keep_terms else "Translate everything, including technical terms. ")
    words = len(text.split())
    system = (f"You are a dubbing translator for Indian enterprise videos. Rewrite the user's transcript as natural, "
              f"conversational spoken {script}, the way a real person in India would say it, not textbook language. {terms}"
              f"Write numbers, amounts and dates as spoken words. The original is {seconds:.0f} seconds and about {words} words; "
              f"keep the dub about the same speaking length (be concise). Output ONLY the translated text.")
    r = check(requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=60,
                            headers={"Authorization": f"Bearer {GROQ_KEY}"},
                            json={"model": GROQ_MODEL, "temperature": 0.3,
                                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}))
    return r.json()["choices"][0]["message"]["content"].strip()


def sync_and_mux(dub_raw, src_wav, inp, d, tag):
    orig, dub = wav_seconds(src_wav), wav_seconds(dub_raw)
    ratio = dub / orig
    synced = d / f"dub_{tag}.wav"
    if abs(ratio - 1) > 0.10:
        ff("-i", str(dub_raw), "-filter:a", f"atempo={min(max(ratio, 0.8), 1.25):.3f}", str(synced))
    else:
        synced.write_bytes(dub_raw.read_bytes())
    final = wav_seconds(synced)
    out = synced
    if inp.suffix.lower() in VIDEO_EXT:
        out = d / f"dubbed_{tag}.mp4"
        ff("-t", str(MAX_SEC), "-i", str(inp), "-i", str(synced), "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out))
    return out, orig, dub, final


def use_credit():
    # ponytail: one global daily cap so a public link can't drain the API credits; per-user limits if it ever matters.
    f = WORK / "usage.json"
    usage = json.loads(f.read_text()) if f.exists() else {}
    today = time.strftime("%Y-%m-%d")
    if usage.get(today, 0) >= MAX_RUNS_PER_DAY:
        raise RuntimeError("Daily demo limit reached. Please try again tomorrow, or watch the demo video.")
    f.write_text(json.dumps({today: usage.get(today, 0) + 1}))


class Job:
    """One uploaded clip: its folder under work/<sha256[:16]>, trimmed 16 kHz wav, and cached API results."""

    def __init__(self, h):
        if not re.fullmatch(r"[0-9a-f]{16}", h or ""):
            raise ValueError("bad job id")
        self.h, self.d = h, WORK / h
        self.inp = next(self.d.glob("input.*"))
        self.src = self.d / "src.wav"
        self.cache_f = self.d / "cache.json"
        self.cache = json.loads(self.cache_f.read_text("utf-8")) if self.cache_f.exists() else {"translations": {}}

    @classmethod
    def create(cls, data, name):
        h = hashlib.sha256(data).hexdigest()[:16]
        d = WORK / h
        d.mkdir(parents=True, exist_ok=True)
        inp = d / f"input{Path(name).suffix.lower()}"
        if not inp.exists():
            inp.write_bytes(data)
        if not (d / "src.wav").exists():
            ff("-i", str(inp), "-t", str(MAX_SEC), "-vn", "-ac", "1", "-ar", "16000", str(d / "src.wav"))
        return cls(h)

    def save(self):
        self.cache_f.write_text(json.dumps(self.cache, ensure_ascii=False), "utf-8")

    def url(self, p):
        return f"/media/{self.h}/{p.name}?v={int(p.stat().st_mtime)}"

    def synth(self, text, lang, mode):
        use_credit()
        raw = self.d / f"raw_{lang}_{mode}.wav"
        tts(text, lang, mode, self.cache.get("embedding"), raw)
        out, orig, dub, final = sync_and_mux(raw, self.src, self.inp, self.d, f"{lang}_{mode}")
        return {"output_url": self.url(out), "output_is_video": out.suffix == ".mp4",
                "download_name": f"bhasha_dub_{lang.lower()}{out.suffix}",
                "original_sec": round(orig, 1), "dubbed_sec": round(dub, 1), "synced_sec": round(final, 1),
                "match": round(100 * min(orig, final) / max(orig, final))}


def timed(fn):
    t = time.perf_counter()
    v = fn()
    return v, round((time.perf_counter() - t) * 1000)


def dub(data, name, lang, mode, keep):
    """Yields one event per pipeline step so the UI can tick them off live."""
    job = Job.create(data, name)
    c = job.cache
    yield {"id": job.h, "input_url": job.url(job.inp), "input_is_video": job.inp.suffix in VIDEO_EXT}

    hit = "transcript" in c
    if not hit:
        (c["transcript"], c["detected"]), ms = timed(lambda: stt(job.src)); job.save()
    yield {"step": 1, "ms": None if hit else ms, "transcript": c["transcript"], "detected": c.get("detected", "?")}

    if mode == "clone":
        hit = "embedding" in c
        if not hit:
            c["embedding"], ms = timed(lambda: clone_embedding(job.src)); job.save()
        yield {"step": 2, "ms": None if hit else ms}
    else:
        yield {"step": 2, "skipped": True}

    ck = f"{lang}|{keep}"
    hit = ck in c["translations"]
    if not hit:
        c["translations"][ck], ms = timed(lambda: translate(c["transcript"], lang, wav_seconds(job.src), keep)); job.save()
    yield {"step": 3, "ms": None if hit else ms, "translation": c["translations"][ck]}

    res, ms = timed(lambda: job.synth(c["translations"][ck], lang, mode))
    yield {"step": 4, "ms": ms, **res}
