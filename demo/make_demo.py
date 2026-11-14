"""Builds demo/bhasha_dub_demo.mp4: a 1080x1080 ~60 s demo from real app screenshots, real dubs and Timbre narration.

Run from the repo root:  python demo/make_demo.py
Needs .env keys, Microsoft Edge, and `pip install playwright`. Re-runs reuse everything already generated in demo/build/.
"""
import html, re, subprocess, sys, time, socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pipeline as P  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

B = ROOT / "demo" / "build"
B.mkdir(parents=True, exist_ok=True)
LONG = "--long" in sys.argv  # 2-3 min cut for the submission form; default is the ~60 s social cut
OUT = ROOT / "demo" / ("bhasha_dub_demo_long.mp4" if LONG else "bhasha_dub_demo.mp4")
S = 1080
FPS = 30
CREAM = "#fcf7f2"


def ff(*a):
    P.ff(*a)


def dur(p):
    r = subprocess.run([P.FF, "-i", str(p)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def pause_cut(p, lo, hi):
    """Cut point between words: the last silence starting in [lo, hi] s, else the first one after lo."""
    r = subprocess.run([P.FF, "-i", str(p), "-af", "silencedetect=noise=-35dB:d=0.2", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r)]
    inside = [s for s in starts if lo <= s <= hi]
    return inside[-1] + 0.15 if inside else hi  # no pause in range: hard cut, faded out in segment()


def heard(text, cut, total):
    """Caption = the sentences that roughly fit in the first `cut` seconds of a `total`-second clip."""
    out, chars, n = [], 0, len(text)
    for s in sentences(text):
        if out and (chars + len(s)) / n > cut / total:
            break
        out.append(s); chars += len(s)
    return " ".join(out)


# ---------- 1. audio: real dubs + Timbre narration ----------
def dub_assets():
    data = P.SAMPLE.read_bytes()
    out = {}
    job = P.Job.create(data, P.SAMPLE.name)
    for lang in ["Kannada", "Tamil", "Hindi"]:
        wav = job.d / f"dub_{lang}_clone.wav"
        if not (wav.exists() and f"{lang}|True" in job.cache["translations"]):
            for _ in P.dub(data, P.SAMPLE.name, lang, "clone", True):
                pass
            job = P.Job(job.h)
        out[lang] = (wav, job.cache["translations"][f"{lang}|True"])
    if LONG:
        wav = job.d / "dub_Kannada_timbre.wav"
        if not wav.exists():
            job.synth(job.cache["translations"]["Kannada|True"], "Kannada", "timbre")
        out["Kannada_timbre"] = (wav, job.cache["translations"]["Kannada|True"])
    return out, job


NARRATION = {
    "n1": "Same voice. Three languages. This is Bhasha Dub, built on Gnani A I.",
    "n2": "Banks and insurers record training videos in English. Their customers speak a dozen languages. Dubbing takes weeks.",
    "n3": "So, upload a clip, pick a language, and hit dub.",
    "n4": "Gnani Prisma transcribes the speech. Gnani Voice Clone captures the speaker. An L L M rewrites it the way India actually talks. And it is voiced back, in the same voice.",
    "n5": "Terms like K Y C and E M I stay in English, because that is how we actually say them. Edit any word, and regenerate in seconds.",
    "p_problem": "India's banks, insurers and edtech companies make thousands of training and explainer videos every year, mostly in English. But a loan officer in Hubballi, or a customer in Madurai, learns best in their own language. Localizing one video today means translators, voice artists and a studio. It takes weeks, and the new voice never sounds like the original trainer.",
    "p_steps": "Step one: Gnani Prisma version three transcribes the clip and detects the language automatically, even for Hinglish. Step two: Gnani Voice Clone builds a speaker embedding from just a few seconds of the original audio. Step three: an L L M adapts the script, not as a textbook translation, but the way people actually speak, keeping terms like K Y C, E M I and U P I in English. Step four: the cloned voice speaks the new script, and the audio is time-matched and merged back onto the video.",
    "p_timbre": "No consent to clone a voice? Switch to Gnani's Timbre studio voices, with a native speaker for every language. Here is the same script in Kannada, with a Timbre voice.",
    "p_practical": "Bhasha Dub is built to run cheaply. Transcripts and voice embeddings are cached, so every extra language costs just one synthesis call. Cloning needs explicit consent. And a daily cap stops a public demo from draining A P I credits.",
    "p_usecases": "Use it for K Y C and loan explainers, insurance claim walkthroughs, frontline staff training and product onboarding. In Hindi, Kannada, Tamil, Telugu, Marathi, Bengali, Gujarati, Malayalam, Punjabi and Hinglish.",
    "p_next": "Next on the roadmap: lip sync, full-length videos with chunked processing, and dubbing an entire training library into every language in one click.",
    "n6": "One training video. Every Indian language. The trainer's own voice.",
}


def narration():
    paths = {}
    for k, text in NARRATION.items():
        p = B / f"{k}_{P.hashlib.sha1(text.encode()).hexdigest()[:8]}.wav"
        if not p.exists():
            P.tts(text, "English", "timbre", None, p)
        paths[k] = p
    return paths


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?।])\s+", text) if s.strip()]


# ---------- 2. visuals: title cards, captions, app screenshots ----------
CARD_CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif&display=swap" rel="stylesheet">
<style>
html,body{{margin:0;width:{S}px;height:{S}px;font-family:Inter,'Nirmala UI',sans-serif;}}
.card{{width:{S}px;height:{S}px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;
  background:linear-gradient(180deg,#a2ebfc88 0%,#ffd3b7aa 45%,#e2e0fbaa 80%,{CREAM} 100%),{CREAM};padding:90px;box-sizing:border-box;gap:28px}}
.eyebrow{{font-size:26px;padding:10px 24px;border-radius:99px;background:#ffffffaa;color:#111}}
.big{{font-family:'Instrument Serif','Nirmala UI',serif;font-size:96px;line-height:1.05;color:#000}}
.script{{font-family:'Nirmala UI',sans-serif;font-size:150px;font-weight:600;line-height:1.2;
  background:linear-gradient(90deg,#9f73f4,#fe914b);-webkit-background-clip:text;color:transparent}}
.sub{{font-size:34px;color:#333;max-width:860px}}
.url{{font-size:40px;font-weight:600;background:#000;color:#fff;padding:18px 36px;border-radius:99px}}
.cap{{position:fixed;left:50%;bottom:56px;transform:translateX(-50%);max-width:960px;width:max-content;box-sizing:border-box;
  background:#000000d9;color:#fff;font:600 38px/1.3 Inter,'Nirmala UI',sans-serif;padding:16px 28px;border-radius:22px;text-align:center}}
</style>"""


def render_html(page, body, path, transparent=False):
    page.set_content(f"<html><head>{CARD_CSS}</head><body style='background:{'transparent' if transparent else CREAM}'>{body}</body></html>")
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(path), omit_background=transparent)
    return path


SHOW = {"A I": "AI", "L L M": "LLM", "K Y C": "KYC", "E M I": "EMI", "U P I": "UPI", "A P I": "API", "version three": "v3"}


def caption(page, text, i):
    for k, v in SHOW.items():
        text = text.replace(k, v)
    return render_html(page, f"<div class='cap'>{html.escape(text)}</div>", B / f"cap_{i}.png", transparent=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def app_screens(pw):
    """Drives the real app (local server) through a Hindi dub and screenshots each stage."""
    job = P.Job.create(P.SAMPLE.read_bytes(), P.SAMPLE.name)
    for k in ("transcript", "detected", "embedding"):
        job.cache.pop(k, None)
    job.cache["translations"].pop("Hindi|True", None)
    job.save()
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--port", str(port)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shots = {}
    try:
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=2.4)
        for _ in range(60):
            try:
                page.goto(f"http://127.0.0.1:{port}/")
                break
            except Exception:
                time.sleep(0.5)
        page.evaluate("document.fonts.ready")
        page.wait_for_function("document.querySelector('#rot').textContent.trim() === 'ಕನ್ನಡ'", timeout=30000)
        page.wait_for_timeout(400)
        shots["hero"] = B / "app_hero.png"; page.screenshot(path=str(shots["hero"]))
        page.click("#sampleBtn")
        page.click("#consentRow")
        page.locator(".studio").scroll_into_view_if_needed()
        page.evaluate("window.scrollTo(0, document.querySelector('.studio').offsetTop - 30)")
        shots["studio"] = B / "app_studio.png"; page.screenshot(path=str(shots["studio"]))
        page.click(".seg button[data-mode='timbre']")
        page.click("#langs button:nth-child(2)")
        shots["studio_timbre"] = B / "app_studio_timbre.png"; page.screenshot(path=str(shots["studio_timbre"]))
        page.click(".seg button[data-mode='clone']")
        page.click("#langs button:nth-child(1)")
        page.click("#go")
        page.wait_for_selector("#steps li[data-step='4'].done", timeout=120000)
        page.wait_for_timeout(1200)
        for n in range(1, 5):
            shots[f"step{n}"] = B / f"app_step{n}.png"
            page.locator(f"#steps li[data-step='{n}']").screenshot(path=str(shots[f"step{n}"]))
        page.evaluate("window.scrollTo(0, document.querySelector('#steps').offsetTop - 20)")
        page.wait_for_timeout(500)
        shots["done"] = B / "app_done.png"; page.locator("#results").screenshot(path=str(shots["done"]))
        shots["outcard"] = B / "app_outcard.png"; page.locator(".results .accent").screenshot(path=str(shots["outcard"]))
        browser.close()
    finally:
        srv.terminate()
    return shots


# ---------- 3. assembly ----------
def shot_clip(img, seconds, cap, out, zoom=True):
    frames = max(1, round(seconds * FPS))
    z = "min(zoom+0.0007,1.07)" if zoom else "1"
    fit = (f"scale={S - 80}:{S - 80}:force_original_aspect_ratio=decrease,pad={S}:{S}:(ow-iw)/2:(oh-ih)/2:color={CREAM},"
           f"scale={S * 2}:{S * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={S}x{S}:fps={FPS}")
    args = ["-i", str(img)]
    if cap:
        args += ["-loop", "1", "-i", str(cap)]
        fc = f"[0]{fit}[bg];[bg][1]overlay=0:0:shortest=1,format=yuv420p"
    else:
        fc = f"[0]{fit},format=yuv420p"
    ff(*args, "-filter_complex", fc, "-frames:v", str(frames), "-r", str(FPS),
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out))


_seg = iter(range(1000))


def segment(_unused, audio, shots, cut=None, pad=0.35):
    i = f"{'L' if LONG else 'S'}{next(_seg)}"
    """shots: list of (image, caption_png|None, weight, full_bleed). Duration follows the audio."""
    a = B / f"seg{i}_a.wav"
    fade = f"afade=t=out:st={cut - 0.3:.2f}:d=0.3," if cut else ""
    ff("-i", str(audio), *(["-t", f"{cut:.2f}"] if cut else []), "-af", f"{fade}apad=pad_dur={pad}", "-ar", "44100", "-ac", "1", str(a))
    total = dur(a)
    wsum = sum(s[2] for s in shots)
    parts = []
    for j, (img, cap, w, bleed) in enumerate(shots):
        p = B / f"seg{i}_{j}.mp4"
        shot_clip(img, total * w / wsum, cap, p, zoom=True)
        parts.append(p)
    lst = B / f"seg{i}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    v = B / f"seg{i}_v.mp4"
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(v))
    out = B / f"seg{i}.mp4"
    ff("-i", str(v), "-i", str(a), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out))
    return out


def main():
    with sync_playwright() as pw:
        print("app screenshots…"); app = app_screens(pw)
        print("dubs…"); dubs, job = dub_assets()
        print("narration…"); nar = narration()
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": S, "height": S})
        card = lambda name, body: render_html(page, f"<div class='card'>{body}</div>", B / f"card_{name}.png")
        c_hook = card("hook", "<div class='eyebrow'>Bhasha Dub · built on Gnani.ai</div>"
                              "<div class='big'>This explainer was recorded in English.</div><div class='sub'>Listen.</div>")
        c_kn = card("kn", "<div class='sub'>Same voice. Now in</div><div class='script'>ಕನ್ನಡ</div>")
        c_ta = card("ta", "<div class='sub'>…and</div><div class='script'>தமிழ்</div>")
        c_end = card("end", "<div class='big'>One training video.<br>Every Indian language.<br>The trainer's own voice.</div>"
                            "<div class='url'>bhasha-dub.onrender.com</div>"
                            "<div class='sub'>Gnani Prisma · Voice Clone · Timbre<br>#GnaniAI #GreatIndianAIInternshipChallenge</div>")
        c_problem = card("problem", "<div class='eyebrow'>The problem</div><div class='big'>Weeks of studio dubbing.<br>A stranger's voice.</div>")
        c_langs = card("langs", "<div class='eyebrow'>Use cases</div><div class='big' style='font-size:64px'>KYC &amp; loan explainers<br>Claim walkthroughs<br>Frontline training</div>"
                                "<div class='sub' style='font-family:Nirmala UI;font-size:38px;line-height:1.6'>हिन्दी · ಕನ್ನಡ · தமிழ் · తెలుగు · मराठी<br>বাংলা · ગુજરાતી · മലയാളം · ਪੰਜਾਬੀ · Hinglish</div>")
        c_next = card("next", "<div class='eyebrow'>What's next</div><div class='big'>Lip sync<br>Full-length videos<br>Whole training libraries</div>")
        caps = iter(range(1000))
        cap = lambda t: caption(page, t, next(caps))

        segs = []
        # Hook: the original English sample, first sentence or two
        orig = job.src
        transcript = job.cache["transcript"]
        c = pause_cut(orig, 3.5, 5.0)
        segs.append(segment(0, orig, [(c_hook, cap(heard(transcript, c, dur(orig))), 1, False)], cut=c))
        # Kannada + Tamil dubs (real cloned-voice output)
        for i, (lang, c) in enumerate([("Kannada", c_kn), ("Tamil", c_ta)], start=1):
            wav, text = dubs[lang]
            cut = pause_cut(wav, 4.0, 6.0)
            segs.append(segment(i, wav, [(c, cap(heard(text, cut, dur(wav))), 1, False)], cut=cut))
        # Narrated walkthrough over real app screenshots
        n1 = sentences(NARRATION["n1"])
        segs.append(segment(3, nar["n1"], [(app["hero"], cap(" ".join(n1[:2])), 1, True), (app["hero"], cap(n1[2]), 1, True)]))
        if LONG:
            segs.append(segment(4, nar["p_problem"], [(c_problem, cap(s), len(s), False) for s in sentences(NARRATION["p_problem"])]))
        else:
            segs.append(segment(4, nar["n2"], [(app["hero"], cap(s), len(s), True) for s in sentences(NARRATION["n2"])]))
        segs.append(segment(5, nar["n3"], [(app["studio"], cap(NARRATION["n3"]), 1, True)]))
        key = "p_steps" if LONG else "n4"
        segs.append(segment(6, nar[key], [(app[f"step{k + 1}"], cap(s), len(s), False) for k, s in enumerate(sentences(NARRATION[key]))]))
        hi_wav, hi_text = dubs["Hindi"]
        cut = pause_cut(hi_wav, 9.0, 12.0) if LONG else pause_cut(hi_wav, 4.0, 6.0)
        segs.append(segment(7, hi_wav, [(app["done"], cap(heard(hi_text, cut, dur(hi_wav))), 1, True)], cut=cut))
        segs.append(segment(8, nar["n5"], [(app["outcard"], cap(s), len(s), False) for s in sentences(NARRATION["n5"])]))
        if LONG:
            segs.append(segment(0, nar["p_timbre"], [(app["studio_timbre"], cap(s), len(s), True) for s in sentences(NARRATION["p_timbre"])]))
            kt_wav, kt_text = dubs["Kannada_timbre"]
            cut = pause_cut(kt_wav, 5.0, 7.0)
            segs.append(segment(0, kt_wav, [(app["studio_timbre"], cap(heard(kt_text, cut, dur(kt_wav))), 1, True)], cut=cut))
            segs.append(segment(0, nar["p_practical"], [(app["studio"], cap(s), len(s), True) for s in sentences(NARRATION["p_practical"])]))
            segs.append(segment(0, nar["p_usecases"], [(c_langs, cap(s), len(s), False) for s in sentences(NARRATION["p_usecases"])]))
            segs.append(segment(0, nar["p_next"], [(c_next, cap(NARRATION["p_next"]), 1, False)]))
        segs.append(segment(9, nar["n6"], [(c_end, None, 1, False)], pad=1.5))
        browser.close()

    lst = B / ("all_long.txt" if LONG else "all.txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs))
    ff("-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(OUT))
    print(f"done: {OUT}  ({dur(OUT):.1f}s)")


if __name__ == "__main__":
    main()
