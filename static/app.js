const $ = (s) => document.querySelector(s);
const state = { file: null, sample: false, lang: "Hindi", mode: "clone", id: null };
const NATIVE = { Hindi: "हिन्दी", Kannada: "ಕನ್ನಡ", Tamil: "தமிழ்", Telugu: "తెలుగు", Marathi: "मराठी", Bengali: "বাংলা",
  Gujarati: "ગુજરાતી", Malayalam: "മലയാളം", Punjabi: "ਪੰਜਾਬੀ", Hinglish: "Hinglish", English: "English" };

// Rotating headline word
const words = Object.values(NATIVE).slice(0, 9);
let wi = 0;
setInterval(() => {
  const r = $("#rot"); r.classList.add("out");
  setTimeout(() => { r.textContent = words[++wi % words.length]; r.classList.remove("out"); }, 300);
}, 2200);

function showErr(msg) { const e = $("#err"); e.textContent = msg || ""; e.hidden = !msg; }
function canGo() { $("#go").disabled = !(state.file || state.sample) || (state.mode === "clone" && !$("#consent").checked); }
function mediaEl(url, isVideo) {
  const m = document.createElement(isVideo ? "video" : "audio");
  m.src = url; m.controls = true; m.preload = "metadata"; if (isVideo) m.playsInline = true;
  return m;
}

// Languages
fetch("/api/config").then((r) => r.json()).then((c) => {
  const box = $("#langs");
  c.languages.forEach((l) => {
    const b = document.createElement("button");
    b.type = "button"; b.role = "radio"; b.textContent = l === "English" || l === "Hinglish" ? l : `${l} · ${NATIVE[l]}`;
    b.className = l === state.lang ? "on" : "";
    b.onclick = () => { state.lang = l; [...box.children].forEach((x) => x.classList.toggle("on", x === b)); };
    box.appendChild(b);
  });
  if (!c.ready) showErr("Server is missing API keys.");
});

// Source selection
function setFile(f) {
  state.file = f; state.sample = false;
  $("#drop").classList.add("has");
  $("#dropText").innerHTML = `<b>${f.name.replace(/[<>&]/g, "")}</b><br><small>${(f.size / 1e6).toFixed(1)} MB · click to change</small>`;
  canGo();
}
$("#file").onchange = (e) => e.target.files[0] && setFile(e.target.files[0]);
const drop = $("#drop");
drop.onkeydown = (e) => (e.key === "Enter" || e.key === " ") && $("#file").click();
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && setFile(e.dataTransfer.files[0]));
$("#sampleBtn").onclick = () => {
  state.sample = true; state.file = null; $("#file").value = "";
  drop.classList.add("has");
  $("#dropText").innerHTML = "<b>Sample: English KYC explainer</b><br><small>15 s · click to upload your own instead</small>";
  canGo();
};

// Voice mode
document.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
  state.mode = b.dataset.mode;
  document.querySelectorAll(".seg button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); });
  $("#consentRow").hidden = state.mode !== "clone";
  canGo();
});
$("#consent").onchange = canGo;

// Pipeline
function step(n, cls, label) {
  const li = $(`#steps li[data-step="${n}"]`);
  if (!li) return;
  li.className = cls; li.querySelector("em").textContent = label || "";
}
function showOutput(r) {
  $("#outMedia").replaceChildren(mediaEl(r.output_url, r.output_is_video));
  $("#match").textContent = `${r.match}% length match`;
  $("#stats").textContent = `Original ${r.original_sec}s · Dub ${r.dubbed_sec}s → synced ${r.synced_sec}s`;
  const a = $("#download"); a.href = r.output_url; a.download = r.download_name;
}

$("#go").onclick = async () => {
  showErr(""); $("#go").disabled = true; $("#go").textContent = "Dubbing…";
  $("#steps").hidden = false; $("#results").hidden = true;
  [1, 2, 3, 4].forEach((n) => step(n, n === 1 ? "active" : "", ""));
  const fd = new FormData();
  fd.append("lang", state.lang); fd.append("mode", state.mode);
  fd.append("keep", $("#keep").checked); fd.append("consent", $("#consent").checked);
  if (state.sample) fd.append("sample", "true"); else fd.append("file", state.file);
  try {
    const res = await fetch("/api/dub", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `Server error ${res.status}`);
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) { handle(JSON.parse(buf.slice(0, i))); buf = buf.slice(i + 1); }
    }
  } catch (e) {
    showErr(e.message);
    document.querySelectorAll("#steps li.active").forEach((li) => (li.className = ""));
  } finally {
    $("#go").textContent = "Localize & Dub"; canGo();
  }
};

function handle(ev) {
  if (ev.error) throw new Error(ev.error);
  if (ev.id) {
    state.id = ev.id;
    const url = state.file ? URL.createObjectURL(state.file) : ev.input_url;
    $("#origMedia").replaceChildren(mediaEl(url, ev.input_is_video));
    $("#outTitle").textContent = state.lang === "English" || state.lang === "Hinglish" ? state.lang : `${state.lang} · ${NATIVE[state.lang]}`;
    $("#outMedia").replaceChildren(); $("#stats").textContent = ""; $("#match").textContent = "";
    return;
  }
  const label = ev.skipped ? "skipped" : ev.ms == null ? "cached ⚡" : `${(ev.ms / 1000).toFixed(1)} s`;
  step(ev.step, ev.skipped ? "skip" : "done", label);
  step(ev.step + 1, "active", "");
  if (ev.step === 1) { $("#transcript").textContent = ev.transcript; $("#detected").textContent = `Detected: ${ev.detected}`; }
  if (ev.step === 3) { $("#translation").value = ev.translation; $("#results").hidden = false; }
  if (ev.step === 4) { showOutput(ev); $("#results").scrollIntoView({ behavior: "smooth", block: "start" }); }
}

$("#resynth").onclick = async () => {
  const b = $("#resynth"); b.disabled = true; b.textContent = "Re-synthesizing…"; showErr("");
  try {
    const res = await fetch("/api/resynth", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: state.id, lang: state.lang, mode: state.mode, text: $("#translation").value, consent: $("#consent").checked }) });
    const j = await res.json();
    if (!res.ok) throw new Error(j.detail || "Re-synthesis failed");
    showOutput(j); $("#outMedia").firstChild.play().catch(() => {});
  } catch (e) { showErr(e.message); } finally { b.disabled = false; b.textContent = "↻ Re-synthesize"; }
};
