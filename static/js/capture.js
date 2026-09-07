import { api } from "./api.js";

const FALLBACK_MAX_SECONDS = 600;
const mimeCandidates = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

function pickMime() {
  if (!window.MediaRecorder) return "";
  return mimeCandidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function mmss(total) {
  const minutes = Math.floor(total / 60);
  const seconds = String(total % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function renderCapture(root, me) {
  document.title = "Ny ide";
  document.body.classList.add("capture-mode");
  root.innerHTML = `
    <div class="capture-wrap">
      <div class="capture-stage" id="stage"></div>
    </div>
  `;
  const stage = root.querySelector("#stage");
  const state = {
    media: null,
    recorder: null,
    chunks: [],
    timer: null,
    elapsed: 0,
    sending: false,
    mime: pickMime(),
    maxSeconds: Number(me?.max_record_seconds) || FALLBACK_MAX_SECONDS,
  };

  function paintIdle(message) {
    stage.innerHTML = `
      <img class="capture-logo" src="/static/brand/a4-logo.svg" alt="A4" />
      <h1>Ny ide</h1>
      <p class="timer">${mmss(0)} / ${mmss(state.maxSeconds)}</p>
      <button class="rec-btn" id="main-btn" type="button">Start</button>
      <p class="hint">${message || "Tryk for at optage. Stop når du er færdig — resten kører af sig selv."}</p>
      ${backLink()}
      ${installHint()}
    `;
    stage.querySelector("#main-btn").addEventListener("click", () => begin(state, paint));
  }

  function paintRecording() {
    stage.innerHTML = `
      <img class="capture-logo" src="/static/brand/a4-logo.svg" alt="A4" />
      <h1>Ny ide</h1>
      <p class="timer" id="timer">${mmss(state.elapsed)} / ${mmss(state.maxSeconds)}</p>
      <button class="rec-btn live stop" id="main-btn" type="button">Stop</button>
      <p class="hint">Tal frit. Der er ingen titel og ingen mapper her.</p>
    `;
    stage.querySelector("#main-btn").addEventListener("click", () => stop(state));
  }

  function paintBusy(label) {
    stage.innerHTML = `
      <img class="capture-logo" src="/static/brand/a4-logo.svg" alt="A4" />
      <h1>Ny ide</h1>
      <p class="timer">${label}</p>
      <button class="rec-btn" type="button" disabled>…</button>
      ${backLink()}
    `;
  }

  function paintDone() {
    stage.innerHTML = `
      <div class="done-card">
        <h1>Sendt</h1>
        <p>Optagelsen ligger i indbakken på computeren. Du kan lukke telefonen.</p>
        <button class="primary" id="again" type="button">Endnu en idé</button>
        <a class="ghost" href="/">Til indbakken</a>
      </div>
    `;
    stage.querySelector("#again").addEventListener("click", () => {
      state.elapsed = 0;
      paintIdle();
      begin(state, paint);
    });
  }

  function paint(mode, extra) {
    if (mode === "idle") paintIdle(extra);
    if (mode === "recording") paintRecording();
    if (mode === "busy") paintBusy(extra);
    if (mode === "done") paintDone();
  }

  paint("busy", "Starter mikrofon…");
  begin(state, paint).catch(() => {
    paint("idle", "Tryk Start og giv mikrofontilladelse første gang.");
  });
}

function backLink() {
  return `<a class="capture-back" href="/">Til indbakken</a>`;
}

function installHint() {
  const standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
  if (standalone) return "";
  return `<div class="install-hint">Føj til startskærmen: Chrome-menu → <strong>Tilføj til startskærm</strong>. Ikonet hedder Ny ide og åbner optageren direkte.</div>`;
}

async function begin(state, paint) {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    throw new Error("Din browser kan ikke optage lyd");
  }
  cleanup(state);
  state.media = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.chunks = [];
  const options = state.mime ? { mimeType: state.mime } : {};
  state.recorder = new MediaRecorder(state.media, options);
  state.recorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size) state.chunks.push(event.data);
  });
  state.recorder.addEventListener("stop", () => onStop(state, paint), { once: true });
  state.elapsed = 0;
  state.sending = false;
  state.recorder.start(250);
  paint("recording");
  state.timer = setInterval(() => {
    state.elapsed += 1;
    const timer = document.querySelector("#timer");
    if (timer) timer.textContent = `${mmss(state.elapsed)} / ${mmss(state.maxSeconds)}`;
    if (state.elapsed >= state.maxSeconds) stop(state);
  }, 1000);
}

function stop(state) {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (state.recorder && state.recorder.state !== "inactive") {
    state.recorder.stop();
  } else {
    cleanup(state);
  }
}

async function onStop(state, paint) {
  if (state.sending) return;
  state.sending = true;
  const blob = new Blob(state.chunks, { type: state.recorder?.mimeType || state.mime || "audio/webm" });
  cleanup(state);
  if (!blob.size) {
    state.sending = false;
    paint("idle", "Ingen lyd blev fanget. Prøv igen.");
    return;
  }
  paint("busy", "Sender…");
  const body = new FormData();
  const name = blob.type.includes("mp4") ? "idea.m4a" : "idea.webm";
  body.append("audio", blob, name);
  body.append("source", "pwa");
  try {
    await api("/api/captures", { method: "POST", body });
    paint("done");
  } catch (error) {
    state.sending = false;
    paint("idle", error.message || "Kunne ikke sende. Prøv igen.");
  }
}

function cleanup(state) {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (state.media) {
    state.media.getTracks().forEach((track) => track.stop());
    state.media = null;
  }
  state.recorder = null;
}
