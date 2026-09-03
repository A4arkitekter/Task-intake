import { api, formatWhen } from "./api.js";
import { ensureAuth } from "./login.js";

let poll = null;
let selectedId = null;
let lastHash = "";

export async function renderInbox(root) {
  document.title = "Indbakke · Indtagelse";
  document.body.classList.remove("capture-mode");
  lastHash = "";
  const me = await ensureAuth();
  if (!me) return;

  root.innerHTML = `
    <div class="screen">
      <header class="topbar">
        <a class="brand" href="/">Indtagelse</a>
        <div>
          <a class="ghost" href="/ny-ide">Ny ide</a>
          <button class="linkish" id="logout" type="button">Log ud</button>
        </div>
      </header>
      <div id="whisper-banner"></div>
      <div class="inbox" id="inbox">
        <p class="empty" style="padding:2rem">Henter indbakke…</p>
      </div>
    </div>
  `;
  root.querySelector("#logout").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    location.href = "/login";
  });
  await refresh(root);
  if (poll) clearInterval(poll);
  poll = setInterval(() => refresh(root), 2500);
}

async function refresh(root) {
  const data = await api("/api/inbox");
  const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName || "");
  const hash = JSON.stringify(data);
  if (typing && lastHash) return;
  const banner = root.querySelector("#whisper-banner");
  if (banner) {
    if (data.whisper === "loading") {
      banner.innerHTML = `<div class="banner">Whisper indlæses første gang (lokal model, ~500 MB). Nye optagelser venter i kø.</div>`;
    } else if (data.whisper === "error") {
      banner.innerHTML = `<div class="banner">Whisper kunne ikke starte: ${escapeHtml(data.error || "")}</div>`;
    } else {
      banner.innerHTML = "";
    }
  }
  if (hash === lastHash) return;
  lastHash = hash;
  const captures = data.captures || [];
  if (!selectedId || !captures.some((item) => item.id === selectedId)) {
    selectedId = captures[0]?.id || null;
  }
  const selected = captures.find((item) => item.id === selectedId) || null;
  const mount = root.querySelector("#inbox");
  if (!mount) return;
  mount.innerHTML = `
    <section class="col">
      <h2>Usorteret</h2>
      ${captures.length ? captureList(captures) : `<p class="empty">Ingen idéer i indbakken. Tryk Ny ide på telefonen.</p>`}
    </section>
    <section class="col">
      <h2>Original</h2>
      ${selected ? originalPane(selected) : `<p class="empty">Vælg en optagelse.</p>`}
    </section>
    <section class="col">
      <h2>Forslag</h2>
      ${selected ? proposalPane(selected) : ""}
    </section>
  `;
  mount.querySelectorAll("[data-capture]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedId = button.getAttribute("data-capture");
      refresh(root);
    });
  });
  mount.querySelectorAll("[data-discard-capture]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/captures/${button.getAttribute("data-discard-capture")}/discard`, { method: "POST" });
      selectedId = null;
      refresh(root);
    });
  });
  bindCards(mount, root);
}

function captureList(captures) {
  return `<div class="capture-list">${captures.map((item) => `
    <button type="button" class="capture-item ${item.id === selectedId ? "active" : ""}" data-capture="${item.id}">
      <div class="when">${formatWhen(item.created_at)}</div>
      <div class="preview">${escapeHtml(previewText(item))}</div>
      ${item.status === "processing" ? `<div class="status-pill">Behandler</div>` : ""}
      ${item.status === "error" ? `<div class="status-pill">Fejl</div>` : ""}
    </button>
  `).join("")}</div>`;
}

function originalPane(capture) {
  if (capture.status === "processing") {
    return `<p class="empty">Transskriberer med lokal Whisper…</p>`;
  }
  if (capture.status === "error") {
    return `<p class="empty">${escapeHtml(capture.error_message || "Behandlingen fejlede.")}</p>
      <button class="danger" data-discard-capture="${capture.id}" type="button">Smid optagelsen væk</button>`;
  }
  return `
    <div class="player">
      <div class="muted">${formatWhen(capture.created_at)}${capture.duration_sec ? ` · ${Math.round(capture.duration_sec)} s` : ""}</div>
      <audio controls src="/api/captures/${capture.id}/audio"></audio>
      <div class="transcript">${escapeHtml(capture.transcript || "")}</div>
    </div>
    <p style="margin-top:1rem">
      <button class="danger" data-discard-capture="${capture.id}" type="button">Smid hele optagelsen væk</button>
    </p>
  `;
}

function proposalPane(capture) {
  const pending = (capture.proposals || []).filter((item) => item.status === "pending");
  const sent = (capture.proposals || []).filter((item) => item.status === "sent");
  if (capture.status !== "ready") return "";
  if (!pending.length && !sent.length) {
    return `<p class="empty">Ingen forslag. Smid optagelsen væk, eller optag igen.</p>`;
  }
  return `<div class="cards">
    ${pending.map((item) => cardHtml(item)).join("")}
    ${sent.map((item) => `
      <article class="card sent">
        <strong>${escapeHtml(item.title)}</strong>
        <div class="muted">Klar som mail til Wrike</div>
        <div class="card-actions" style="margin-top:0.6rem">
          <a class="primary" href="/api/proposals/${item.id}/eml">Hent .eml</a>
        </div>
      </article>
    `).join("")}
  </div>`;
}

function cardHtml(item) {
  return `
    <article class="card" data-card="${item.id}">
      <label>Titel (emne)</label>
      <input data-title value="${escapeAttr(item.title)}" />
      <label>Note</label>
      <textarea data-note>${escapeHtml(item.note)}</textarea>
      <div class="card-actions">
        <button class="primary" data-approve type="button">Åbn i Outlook</button>
        <button class="danger" data-discard type="button">Smid væk</button>
      </div>
    </article>
  `;
}

function bindCards(mount, root) {
  mount.querySelectorAll("[data-card]").forEach((card) => {
    const id = card.getAttribute("data-card");
    const title = card.querySelector("[data-title]");
    const note = card.querySelector("[data-note]");
    const save = async () => {
      await api(`/api/proposals/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title.value, note: note.value }),
      });
    };
    title.addEventListener("change", save);
    note.addEventListener("change", save);
    card.querySelector("[data-discard]").addEventListener("click", async () => {
      await api(`/api/proposals/${id}/discard`, { method: "POST" });
      refresh(root);
    });
    card.querySelector("[data-approve]").addEventListener("click", async () => {
      const approve = card.querySelector("[data-approve]");
      approve.disabled = true;
      try {
        await save();
        const payload = await api(`/api/proposals/${id}/approve`, { method: "POST" });
        await refresh(root);
        if (payload.mailto) {
          location.href = payload.mailto;
        }
      } catch (error) {
        approve.disabled = false;
        alert(error.message);
      }
    });
  });
}

function previewText(capture) {
  if (capture.status === "processing") return "På vej…";
  if (capture.status === "error") return capture.error_message || "Fejl";
  const first = (capture.proposals || []).find((item) => item.status === "pending");
  return first?.title || capture.transcript || "Optagelse";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}
