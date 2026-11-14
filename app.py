"""Bhasha Dub: dub a short clip into Indian languages in the speaker's own voice (Gnani Prisma + Voice Clone + Timbre, Groq for translation)."""
import hashlib, json, os, subprocess, time, wave
from pathlib import Path

import imageio_ffmpeg
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
GNANI = "https://api.vachana.ai"
KEY = os.getenv("GNANI_API_KEY", "")
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
FF = imageio_ffmpeg.get_ffmpeg_exe()
WORK = Path(__file__).with_name("work")
MAX_SEC = 20  # credit guardrail; also under Prisma's 30s REST limit

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


# ---------------- UI ----------------
st.set_page_config(page_title="Bhasha Dub", page_icon="🎙️", layout="wide")
st.title("🎙️ Bhasha Dub")
st.caption("One explainer video → every Indian language, in the speaker's own voice · "
           "Powered by Gnani.ai Prisma v3.0 · Voice Clone v1 · Timbre v2.5")
if not KEY or not GROQ_KEY:
    st.error("Set GNANI_API_KEY and GROQ_API_KEY in a .env file next to app.py, then restart.")
    st.stop()

c1, c2, c3 = st.columns([2, 1, 1])
up = c1.file_uploader("Video or audio clip (first 20 s is used)", type=["mp4", "mov", "webm", "wav", "mp3", "m4a"])
lang = c2.selectbox("Dub into", list(LANGS))
mode = c3.radio("Voice", ["clone", "timbre"], format_func=lambda m: "Clone original speaker" if m == "clone" else "Gnani studio voice")
keep = c2.toggle("Keep English domain terms (KYC, EMI…)", value=True)
consent = c3.checkbox("I have the speaker's consent to clone this voice")

if not up:
    st.info("Upload a short clip to start. Tip: use a slides/screen-recording style video, since lips are not re-synced.")
    st.stop()

data = up.getvalue()
h = hashlib.sha256(data).hexdigest()[:16]
d = WORK / h
d.mkdir(parents=True, exist_ok=True)
inp = d / f"input{Path(up.name).suffix.lower()}"
if not inp.exists():
    inp.write_bytes(data)
src = d / "src.wav"
if not src.exists():
    ff("-i", str(inp), "-t", str(MAX_SEC), "-vn", "-ac", "1", "-ar", "16000", str(src))
cache_f = d / "cache.json"
cache = json.loads(cache_f.read_text("utf-8")) if cache_f.exists() else {"translations": {}}
save = lambda: cache_f.write_text(json.dumps(cache, ensure_ascii=False), "utf-8")
tkey = f"tr_{h}_{lang}_{keep}"


def synth(text):
    t = time.perf_counter()
    raw = d / f"raw_{lang}_{mode}.wav"
    tts(text, lang, mode, cache.get("embedding"), raw)
    out, orig, dub, final = sync_and_mux(raw, src, inp, d, f"{lang}_{mode}")
    st.session_state[f"out_{h}_{lang}"] = {"path": str(out), "stats": (orig, dub, final), "ms": (time.perf_counter() - t) * 1000}


if st.button("🚀 Localize & Dub Now", type="primary", disabled=mode == "clone" and not consent):
    try:
        with st.status("Running pipeline…", expanded=True) as s:
            steps = [
                ("1. Prisma STT transcription", "transcript", lambda: dict(zip(("transcript", "detected"), stt(src)))),
                ("2. Speaker embedding extraction", "embedding", lambda: {"embedding": clone_embedding(src)}),
            ]
            for label, k, fn in steps:
                if k == "embedding" and mode != "clone":
                    continue
                t = time.perf_counter()
                hit = k in cache
                if not hit:
                    cache.update(fn()); save()
                st.write(f"✅ {label} — {'cached' if hit else f'{(time.perf_counter() - t) * 1000:.0f} ms'}")
            t = time.perf_counter()
            ck = f"{lang}|{keep}"
            if ck not in cache["translations"]:
                cache["translations"][ck] = translate(cache["transcript"], lang, wav_seconds(src), keep); save()
            st.session_state[tkey] = cache["translations"][ck]
            st.write(f"✅ 3. Code-mixed cultural adaptation — {(time.perf_counter() - t) * 1000:.0f} ms")
            synth(st.session_state[tkey])
            st.write(f"✅ 4. Voice synthesis & sync — {st.session_state[f'out_{h}_{lang}']['ms']:.0f} ms")
            s.update(label="Done", state="complete")
    except Exception as e:
        st.error(str(e))

left, right = st.columns(2)
with left:
    st.subheader("Original")
    (st.video if inp.suffix in VIDEO_EXT else st.audio)(str(inp))
    if "transcript" in cache:
        st.caption(f"Detected language: {cache.get('detected', '?')}")
        st.text_area("Source transcript", cache["transcript"], height=150, disabled=True)
with right:
    st.subheader(f"Localized · {lang}")
    res = st.session_state.get(f"out_{h}_{lang}")
    if res:
        p = Path(res["path"])
        (st.video if p.suffix == ".mp4" else st.audio)(str(p))
        o, dub, fin = res["stats"]
        st.caption(f"Original {o:.1f}s · Dubbed {dub:.1f}s → synced {fin:.1f}s · Match {100 * min(o, fin) / max(o, fin):.0f}%")
        st.download_button("⬇️ Download", p.read_bytes(), file_name=f"bhasha_dub_{lang.lower()}{p.suffix}")
    if tkey in st.session_state:
        edited = st.text_area("Translated script (edit a word and re-synthesize)", key=tkey, height=150)
        if st.button("🔁 Re-synthesize edit"):
            try:
                synth(edited); st.rerun()
            except Exception as e:
                st.error(str(e))
