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
  const hash = `${selectedId}:${JSON.stringify(data)}`;
  if (typing && lastHash) return;
  const banner = root.querySelector("#whisper-banner");
    if (banner) {
      const parts = [];
      if (data.whisper === "loading") {
        parts.push(`<div class="banner">Whisper indlæses første gang (lokal model, ~500 MB). Nye optagelser venter i kø.</div>`);
      } else if (data.whisper === "error") {
        parts.push(`<div class="banner">Whisper kunne ikke starte: ${escapeHtml(data.error || "")}</div>`);
      }
      if (data.rewrite === "unavailable" || data.rewrite === "error") {
        parts.push(`<div class="banner">Overskrifter bruger rå tekst, indtil Ollama kører (${escapeHtml(data.rewrite_model || "qwen2.5:14b")}). ${escapeHtml(data.rewrite_error || "")}</div>`);
      }
      banner.innerHTML = parts.join("");
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
      <p class="col-hint">Optagelser du endnu ikke har sendt til Wrike. Klik en for at se den til højre.</p>
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
      ${rawSnippet(item) ? `<div class="sub">${escapeHtml(rawSnippet(item))}</div>` : ""}
      ${item.status === "processing" ? `<div class="status-pill">Behandler</div>` : ""}
      ${item.status === "error" ? `<div class="status-pill">Fejl</div>` : ""}
    </button>
  `).join("")}</div>`;
}

function originalPane(capture) {
  if (capture.status === "processing") {
    return `<p class="empty">Transskriberer og skriver overskrift…</p>`;
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
  const pending = (capture.proposals || []).filter((item) => item.status === "pending").slice(0, 1);
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
        <button class="ghost" data-rewrite type="button">Genskab overskrift</button>
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
    const rewriteBtn = card.querySelector("[data-rewrite]");
    if (rewriteBtn) {
      rewriteBtn.addEventListener("click", async () => {
        rewriteBtn.disabled = true;
        rewriteBtn.textContent = "Skriver overskrift…";
        try {
          await api(`/api/captures/${selectedId}/rewrite`, { method: "POST" });
          lastHash = "";
          await refresh(root);
        } catch (error) {
          rewriteBtn.disabled = false;
          rewriteBtn.textContent = "Genskab overskrift";
          alert(error.message);
        }
      });
    }
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
  const pending = (capture.proposals || []).find((item) => item.status === "pending");
  return pending?.title || "Optagelse";
}

function rawSnippet(capture) {
  if (capture.status !== "ready") return "";
  const text = (capture.transcript || "").trim();
  if (!text) return "";
  return text.length > 70 ? `${text.slice(0, 70)}…` : text;
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
