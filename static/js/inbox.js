import { api, formatWhen } from "./api.js?v=14";
import { ensureAuth } from "./login.js?v=14";

let poll = null;
let onVisible = null;
let updateActionToken = "";
let serverInstanceId = "";
let updateOutcomeShown = false;
let lastJobsHash = "";
let folderTimer = null;
const UPDATE_RESULT_KEY = "indtagelse-update-result";

export async function renderInbox(root) {
  document.title = "Administration · Indtagelse";
  document.body.classList.remove("capture-mode");
  lastJobsHash = "";
  const me = await ensureAuth();
  if (!me) return;

  root.innerHTML = `
    <div class="screen">
      <header class="topbar">
        <a class="brand brand-on-dark" href="/">
          <img class="brand-logo" src="/static/brand/a4-logo.svg" alt="A4" />
          <span class="brand-product">Indtagelse</span>
        </a>
        <div class="topbar-actions">
          <a class="ghost" href="/ny-ide">Ny ide</a>
        </div>
      </header>
      <div id="update-box" class="update-box" hidden>
        <strong id="update-title">En opdatering er klar</strong>
        <div id="update-message" class="muted">Programmet kan opdateres og genstartes automatisk.</div>
        <div class="row">
          <button id="update-btn" class="primary" type="button">Opdatér og genstart</button>
        </div>
      </div>
      <div class="dashboard" id="dashboard">
        <p class="empty" style="padding:2rem">Henter administration…</p>
      </div>
    </div>
  `;
  root.querySelector("#update-btn").addEventListener("click", applyUpdate);
  await loadDashboard(root);
  initUpdateBanner();
  if (poll) clearInterval(poll);
  poll = setInterval(() => refreshJobs(root), 10000);
  if (onVisible) document.removeEventListener("visibilitychange", onVisible);
  onVisible = () => {
    if (document.visibilityState === "visible") refreshJobs(root);
  };
  document.addEventListener("visibilitychange", onVisible);
}

async function loadDashboard(root) {
  const data = await api("/api/admin");
  const mount = root.querySelector("#dashboard");
  if (!mount) return;
  const settings = data.settings || {};
  mount.innerHTML = `
    <div class="dash-grid">
      <section class="dash-card dash-status">
        <p class="dash-kicker">Status</p>
        <h2>System</h2>
        <div id="lamps" class="lamps">${lampsHtml(data.health || {})}</div>
        <a class="ghost" href="/api/admin/report">Hent fejlrapport.zip</a>
      </section>
      <section class="dash-card dash-settings">
        <p class="dash-kicker">Indstillinger</p>
        <h2>Wrike-nøgler</h2>
        ${wrikeKeysHtml(settings)}
        <h2>Hvor lander opgaverne</h2>
        <div class="field">
          <label for="inbox-dir">Mappe med optagelser</label>
          <div class="row-input">
            <input id="inbox-dir" value="${escapeAttr(settings.inbox_dir || "")}" />
            <button class="primary" id="save-inbox" type="button">Gem sti</button>
          </div>
        </div>
        <div class="field">
          <label for="remind-to">Din arbejdmail</label>
          <div class="row-input">
            <input id="remind-to" value="${escapeAttr(settings.remind_to || "")}" placeholder="navn@a4.dk" />
            <button class="primary" id="save-remind" type="button">Gem mail</button>
          </div>
          <p class="col-hint">Bruges kun, hvis et job fejler.</p>
        </div>
        <div class="field">
          <span class="field-label">Wrike konto</span>
          <div id="selected-assignee" class="field-value">${selectedAssigneeHtml(settings)}</div>
          ${tokenOwnerHint(settings)}
        </div>
        <div class="field">
          <span class="field-label">Wrike-mappe</span>
          <div id="selected-folder" class="field-value">${selectedFolderHtml(settings)}</div>
          <input id="folder-search" placeholder="Søg i dine mapper…" />
          <div id="folder-results" class="folder-results"></div>
        </div>
        <div class="field">
          <label for="importance">Prioritet</label>
          <select id="importance">
            <option value="High"${settings.wrike_importance === "High" ? " selected" : ""}>High</option>
            <option value="Normal"${settings.wrike_importance === "Normal" ? " selected" : ""}>Normal</option>
            <option value="Low"${settings.wrike_importance === "Low" ? " selected" : ""}>Low</option>
          </select>
        </div>
        <div class="card-actions">
          <button class="primary" id="test-wrike" type="button">Opret testopgave</button>
        </div>
        <p id="settings-msg" class="field-msg" hidden></p>
      </section>
    </div>
    <section class="dash-card dash-catalog">
      <p class="dash-kicker">Katalog</p>
      <h2>Transkriptioner · 30 dage</h2>
      <p class="col-hint">Teksten gemmes her, også efter den er sendt til Wrike. Slet-ikonet fjerner kun linjen her — ikke opgaven i Wrike.</p>
      <input id="catalog-search" placeholder="Søg i titel eller transkription…" />
      <div id="jobs">${jobsHtml(data.jobs || [])}</div>
    </section>
  `;
  lastJobsHash = jobsHash(data);
  bindSettings(root);
  bindJobActions(root);
}

function bindSettings(root) {
  const saveInbox = root.querySelector("#save-inbox");
  const inbox = root.querySelector("#inbox-dir");
  const saveRemind = root.querySelector("#save-remind");
  const remindTo = root.querySelector("#remind-to");
  const saveKeys = root.querySelector("#save-wrike-keys");
  const importance = root.querySelector("#importance");
  const search = root.querySelector("#folder-search");
  const testBtn = root.querySelector("#test-wrike");
  saveInbox?.addEventListener("click", async () => {
    await saveSettings(root, { inbox_dir: inbox.value });
  });
  saveRemind?.addEventListener("click", async () => {
    await saveSettings(root, { remind_to: remindTo.value });
  });
  saveKeys?.addEventListener("click", async () => {
    await saveWrikeKeys(root);
  });
  importance?.addEventListener("change", async () => {
    await saveSettings(root, { wrike_importance: importance.value });
  });
  search?.addEventListener("input", () => {
    clearTimeout(folderTimer);
    folderTimer = setTimeout(() => searchFolders(root, search.value), 250);
  });
  testBtn?.addEventListener("click", async () => {
    testBtn.disabled = true;
    testBtn.textContent = "Opretter…";
    try {
      const data = await api("/api/admin/wrike/test", { method: "POST" });
      const url = data.task?.url;
      setSettingsMsg(root, url ? `Testopgave oprettet. Åbn i Wrike.` : "Testopgave oprettet.");
      if (url) window.open(url, "_blank", "noopener");
    } catch (error) {
      setSettingsMsg(root, error.message);
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "Opret testopgave";
    }
  });
  const catalogSearch = root.querySelector("#catalog-search");
  catalogSearch?.addEventListener("input", () => applyCatalogFilter(root));
}

async function saveSettings(root, body) {
  try {
    const data = await api("/api/admin/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (data.settings) {
      const selected = root.querySelector("#selected-folder");
      const assignee = root.querySelector("#selected-assignee");
      if (selected) selected.innerHTML = selectedFolderHtml(data.settings);
      if (assignee) assignee.innerHTML = selectedAssigneeHtml(data.settings);
    }
    setSettingsMsg(root, "Gemt.");
    return data.settings;
  } catch (error) {
    setSettingsMsg(root, error.message);
    throw error;
  }
}

async function searchFolders(root, query) {
  const box = root.querySelector("#folder-results");
  if (!box) return;
  if (!query.trim()) {
    box.innerHTML = "";
    return;
  }
  try {
    const data = await api(`/api/admin/wrike/folders?q=${encodeURIComponent(query.trim())}`);
    const folders = data.folders || [];
    if (!folders.length) {
      const owner = (root.querySelector("[data-token-owner]")?.getAttribute("data-token-owner") || "").trim();
      const hint = owner
        ? ` Ingen mapper matcher. API'et kan kun se mapper som ${owner} har adgang til.`
        : " Ingen mapper matcher. Indsæt Wrike-nøgler først, hvis kontoen ovenfor er tom.";
      box.innerHTML = `<p class="empty">${escapeHtml(hint.trim())}</p>`;
      return;
    }
    box.innerHTML = folders.map((folder) => {
      const label = folder.label || folder.title;
      const meta = folder.subtitle
        ? `<small class="folder-meta">${escapeHtml(folder.subtitle)}</small>`
        : "";
      return `
      <button type="button" class="folder-item" data-folder-id="${escapeAttr(folder.id)}" data-folder-title="${escapeAttr(label)}">
        <span>${escapeHtml(folder.title)}</span>
        ${meta}
      </button>`;
    }).join("");
    box.querySelectorAll("[data-folder-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        await saveSettings(root, {
          wrike_folder_id: button.getAttribute("data-folder-id"),
          wrike_folder_name: button.getAttribute("data-folder-title"),
        });
        const search = root.querySelector("#folder-search");
        if (search) search.value = "";
        box.innerHTML = "";
      });
    });
  } catch (error) {
    box.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function jobsHash(data) {
  return JSON.stringify({
    health: data.health,
    waiting: data.waiting,
    jobs: (data.jobs || []).map((job) => [
      job.id,
      job.status,
      job.error_message,
      (job.proposals || []).map((item) => [item.status, item.wrike_url]),
    ]),
  });
}

async function refreshJobs(root, { force = false } = {}) {
  if (!force && ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) return;
  if (!force && root.querySelector("details[open]")) return;
  try {
    const pulse = await api("/api/admin/pulse");
    const lamps = root.querySelector("#lamps");
    if (lamps) lamps.innerHTML = lampsHtml(pulse.health || {});
    const hash = jobsHash(pulse);
    if (!force && hash === lastJobsHash) return;
    const data = await api("/api/admin");
    lastJobsHash = jobsHash(data);
    const jobs = root.querySelector("#jobs");
    if (jobs) {
      jobs.innerHTML = jobsHtml(data.jobs || []);
      bindJobActions(root);
      applyCatalogFilter(root);
    }
  } catch (_ignored) {
    // En midlertidig genstart må ikke tømme skærmen.
  }
}

function bindJobActions(root) {
  root.querySelectorAll("[data-retry-capture]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Prøver igen…";
      try {
        await api(`/api/captures/${button.getAttribute("data-retry-capture")}/retry`, { method: "POST" });
        await refreshJobs(root, { force: true });
      } catch (error) {
        button.disabled = false;
        button.textContent = "Prøv igen";
        alert(error.message);
      }
    });
  });
  root.querySelectorAll("[data-delete-capture]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Fjern transkriptionen fra kataloget? Opgaven i Wrike bliver.")) return;
      button.disabled = true;
      try {
        await api(`/api/captures/${button.getAttribute("data-delete-capture")}`, { method: "DELETE" });
        await refreshJobs(root, { force: true });
      } catch (error) {
        button.disabled = false;
        alert(error.message);
      }
    });
  });
}

function lampsHtml(health) {
  const items = [
    ["Optagelser", health.inbox],
    ["Wrike API", health.wrike],
    ["Behandling", health.behandling],
  ];
  return items.map(([label, lamp]) => {
    const level = lamp?.level || "red";
    const message = lamp?.message || "Ukendt";
    return `<div class="lamp lamp-${escapeAttr(level)}"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(message)}</span></div>`;
  }).join("");
}

function selectedFolderHtml(settings) {
  if (!(settings.wrike_token_owner || settings.wrike_assignee_id)) {
    return "Indsæt Wrike-nøgler først.";
  }
  if (settings.wrike_folder_name || settings.wrike_folder_id) {
    const extra = settings.wrike_folder_defaulted ? " · valgt automatisk, du kan skifte" : "";
    return `${escapeHtml(settings.wrike_folder_name || settings.wrike_folder_id)}${escapeHtml(extra)}`;
  }
  return "Ingen mappe valgt. Søg nedenfor.";
}

function selectedAssigneeHtml(settings) {
  const owner = (settings.wrike_token_owner || settings.wrike_assignee_name || "").trim();
  const id = settings.wrike_token_owner_id || settings.wrike_assignee_id || "";
  if (owner) {
    return `<span data-account-id="${escapeAttr(id)}">${escapeHtml(owner)}</span>`;
  }
  return `<span data-account-id="">Nøglerne er ikke sat endnu.</span>`;
}

function tokenOwnerHint(settings) {
  const owner = (settings.wrike_token_owner || "").trim();
  if (owner) {
    return `<p class="col-hint" data-token-owner="${escapeAttr(owner)}">Sådan ser Wrike dine nøgler. Er navnet forkert, skift nøglerne nederst på siden.</p>`;
  }
  return `<p class="col-hint">Indsæt dine Wrike-nøgler nederst på siden. Så vises dit navn her.</p>`;
}

function wrikeKeysHtml(settings) {
  const ready = Boolean(settings.wrike_keys_ready);
  const owner = (settings.wrike_token_owner || "").trim();
  const status = owner
    ? `<p class="col-hint" data-token-owner="${escapeAttr(owner)}">Wrike ser dig som <strong>${escapeHtml(owner)}</strong>. Er det en kollega, skal du lave din egen app og indsætte dine nøgler.</p>`
    : `<p class="col-hint">Hver person laver sin egen Wrike-app. Kopiér ikke nøglerne fra en kollega.</p>`;
  return `
    ${status}
    <ol class="wrike-steps">
      <li>Tryk <a href="https://www.wrike.com/frontend/apps/index.html#/api" target="_blank" rel="noopener">Åbn Wrike API-siden</a>.</li>
      <li>Log ind med <strong>din</strong> arbejdmail, hvis Wrike spørger.</li>
      <li>Tryk <strong>+ App</strong> (Create new app). App-navn: <strong>Indtagelse</strong>. Gem.</li>
      <li>Kopiér <strong>Client ID</strong> (det grå felt under OAuth).</li>
      <li>Kopiér <strong>Secret key</strong>. Tryk øje-ikonet, hvis feltet er stjerner.</li>
      <li>Scroll ned til <strong>Permanent access token</strong>. Tryk <strong>Get token</strong> / <strong>Obtain token</strong>. Wrike kan bede om din adgangskode.</li>
      <li>Indsæt de tre værdier her og tryk Gem nøgler. Siden skal vise <strong>dit</strong> navn.</li>
    </ol>
    <p class="col-hint">Client ID og Secret key er din app. Token er dig. “Wrike account A4” betyder firmaets Wrike — ikke at nøglerne må deles.</p>
    <div class="field">
      <label for="wrike-client-id">Client ID</label>
      <input id="wrike-client-id" autocomplete="off" ${ready ? "placeholder=\"Udfyld kun, hvis du skifter nøgler\"" : ""} />
    </div>
    <div class="field">
      <label for="wrike-client-secret">Secret key</label>
      <input id="wrike-client-secret" type="password" autocomplete="off" />
    </div>
    <div class="field">
      <label for="wrike-token">Permanent access token</label>
      <input id="wrike-token" type="password" autocomplete="off" />
    </div>
    <div class="card-actions">
      <button class="primary" id="save-wrike-keys" type="button">${ready ? "Skift nøgler" : "Gem nøgler"}</button>
    </div>
  `;
}

async function saveWrikeKeys(root) {
  const clientId = root.querySelector("#wrike-client-id")?.value.trim() || "";
  const clientSecret = root.querySelector("#wrike-client-secret")?.value.trim() || "";
  const token = root.querySelector("#wrike-token")?.value.trim() || "";
  if (!clientId || !clientSecret || !token) {
    setSettingsMsg(root, "Udfyld alle tre felter: Client ID, Secret key og Permanent access token.");
    return;
  }
  const button = root.querySelector("#save-wrike-keys");
  if (button) {
    button.disabled = true;
    button.textContent = "Tjekker…";
  }
  try {
    const data = await api("/api/admin/wrike/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        token,
      }),
    });
    await loadDashboard(root);
    setSettingsMsg(root, data.message || "Gemt.");
  } catch (error) {
    setSettingsMsg(root, error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Gem nøgler";
    }
  }
}

function jobsHtml(jobs) {
  if (!jobs.length) return `<p class="empty">Ingen transkriptioner de seneste 30 dage.</p>`;
  return `<div class="catalog-list">${jobs.map(jobRow).join("")}</div>`;
}

function jobRow(job) {
  const pending = (job.proposals || []).find((item) => item.status === "pending");
  const sent = (job.proposals || []).find((item) => item.status === "sent");
  const title = sent?.title || pending?.title || (job.status === "processing" ? "Behandler…" : "Optagelse");
  const failed = job.status === "error" || Boolean(job.error_message);
  const status = job.status === "processing"
    ? "Behandler"
    : sent
      ? "I Wrike"
      : failed
        ? "Fejl"
        : "Venter";
  const statusClass = job.status === "processing"
    ? "is-busy"
    : sent
      ? "is-ok"
      : failed
        ? "is-bad"
        : "is-wait";
  const transcript = (job.transcript || "").trim();
  const link = sent?.wrike_url
    ? `<a href="${escapeAttr(sent.wrike_url)}" target="_blank" rel="noopener">Åbn i Wrike</a>`
    : "";
  const retry = failed || pending
    ? `<button class="ghost" data-retry-capture="${job.id}" type="button">Prøv igen</button>`
    : "";
  const search = [title, transcript, job.error_message || ""].join(" ").toLowerCase();
  const body = transcript
    ? `<details class="catalog-text"><summary>Vis transkription</summary><pre>${escapeHtml(transcript)}</pre></details>`
    : "";
  return `
    <article class="catalog-row" data-search="${escapeAttr(search)}">
      <div class="catalog-main">
        <div class="when">${formatWhen(job.created_at)}</div>
        <strong>${escapeHtml(title)}</strong>
        ${job.error_message ? `<div class="sub">${escapeHtml(job.error_message)}</div>` : ""}
        ${body}
      </div>
      <div class="job-meta">
        <span class="status-pill ${statusClass}">${escapeHtml(status)}</span>
        ${link}
        ${retry}
        <button class="icon-btn" type="button" data-delete-capture="${job.id}" aria-label="Slet fra kataloget" title="Slet fra kataloget">
          ${trashIcon()}
        </button>
      </div>
    </article>
  `;
}

function trashIcon() {
  return `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M9 3h6l1 2h5v2H3V5h5l1-2zm1 6h2v9h-2V9zm4 0h2v9h-2V9zM7 9h2v9H7V9zm-1 12h12a1 1 0 0 0 1-1V8H5v12a1 1 0 0 0 1 1z"/></svg>`;
}

function applyCatalogFilter(root) {
  const needle = (root.querySelector("#catalog-search")?.value || "").trim().toLowerCase();
  const rows = root.querySelectorAll(".catalog-row");
  let shown = 0;
  rows.forEach((row) => {
    const match = !needle || (row.getAttribute("data-search") || "").includes(needle);
    row.hidden = !match;
    if (match) shown += 1;
  });
  const empty = root.querySelector("#catalog-empty");
  if (empty) empty.remove();
  if (needle && rows.length && !shown) {
    const jobs = root.querySelector("#jobs");
    if (jobs) {
      const note = document.createElement("p");
      note.className = "empty";
      note.id = "catalog-empty";
      note.textContent = "Ingen transkriptioner matcher søgningen.";
      jobs.append(note);
    }
  }
}

function setSettingsMsg(root, text) {
  const node = root.querySelector("#settings-msg");
  if (!node) return;
  node.textContent = text || "";
  node.hidden = !text;
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

function showUpdateBox(title, message, kind = "info", showButton = false) {
  const box = document.getElementById("update-box");
  const titleEl = document.getElementById("update-title");
  const messageEl = document.getElementById("update-message");
  const button = document.getElementById("update-btn");
  if (!box || !titleEl || !messageEl || !button) return;
  box.hidden = false;
  box.classList.toggle("success", kind === "success");
  box.classList.toggle("error", kind === "error");
  titleEl.textContent = title;
  messageEl.textContent = message;
  button.hidden = !showButton;
  button.disabled = false;
}

function showPreviousUpdateResult() {
  let result = null;
  try {
    result = JSON.parse(sessionStorage.getItem(UPDATE_RESULT_KEY) || "null");
    sessionStorage.removeItem(UPDATE_RESULT_KEY);
  } catch (_ignored) { }
  if (!result) return;
  const resultMessages = {
    updated: "Den nyeste godkendte version er installeret og startet.",
    update_failed: "Opdateringen blev ikke gennemført. Den tidligere version er startet igen. Kør SYSTEMTJEK.bat, hvis fejlen gentager sig.",
    setup_failed: "Programfilerne blev opdateret, men installationen kunne ikke tilpasses automatisk. Kør SETUP.bat og derefter START.bat.",
  };
  updateOutcomeShown = true;
  showUpdateBox(
    result.ok ? "Programmet er opdateret" : "Opdateringen blev ikke gennemført",
    resultMessages[result.code] || result.message || (result.ok ? "Den nyeste version er klar." : "Kør SYSTEMTJEK.bat, og send fejlrapport.zip til IT."),
    result.ok ? "success" : "error",
    !result.ok
  );
}

async function initUpdateBanner() {
  try {
    const health = await fetch("/api/health", { cache: "no-store" }).then((resp) => resp.json());
    serverInstanceId = health.instance_id || serverInstanceId;
    updateActionToken = health.update_action_token || updateActionToken;
  } catch (_ignored) { }
  showPreviousUpdateResult();
  try {
    const resp = await fetch("/api/update/status", { cache: "no-store" });
    const data = await resp.json();
    const update = data.update || {};
    if (update.update_available && !updateOutcomeShown) {
      showUpdateBox(
        "En godkendt opdatering er klar",
        "Klik på knappen. Programmet lukker kortvarigt og starter automatisk igen.",
        "info",
        true
      );
    } else if (!updateOutcomeShown) {
      const box = document.getElementById("update-box");
      if (box) box.hidden = true;
    }
  } catch (_ignored) {
    // En utilgængelig NAS må ikke forstyrre den daglige brug.
  }
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 3500) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForUpdatedServer(previousInstanceId) {
  const deadline = Date.now() + 30 * 60 * 1000;
  let sawOffline = false;
  await new Promise((resolve) => setTimeout(resolve, 1800));
  while (Date.now() < deadline) {
    try {
      const healthResp = await fetchWithTimeout("/api/health", { cache: "no-store" });
      const health = await healthResp.json();
      if (!healthResp.ok || !health.ok) {
        sawOffline = true;
      } else if (sawOffline && health.instance_id && health.instance_id !== previousInstanceId) {
        let result = { ok: true, code: "updated" };
        try {
          const resultResp = await fetchWithTimeout("/api/update/result", { cache: "no-store" });
          const resultData = await resultResp.json();
          if (resultData.result) result = resultData.result;
        } catch (_ignored) { }
        try {
          const statusResp = await fetchWithTimeout("/api/update/status", { cache: "no-store" });
          const statusData = await statusResp.json();
          const update = statusData.update || {};
          if (result.ok && update.update_available) {
            result = { ok: false, code: "update_failed" };
          }
        } catch (_ignored) { }
        try { sessionStorage.setItem(UPDATE_RESULT_KEY, JSON.stringify(result)); } catch (_ignored) { }
        window.location.reload();
        return;
      }
    } catch (_ignored) {
      sawOffline = true;
    }
    await new Promise((resolve) => setTimeout(resolve, 1800));
  }
  showUpdateBox(
    "Opdateringen tager længere end forventet",
    "Kør SYSTEMTJEK.bat, hvis programmet ikke starter igen.",
    "error",
    false
  );
}

async function applyUpdate() {
  const button = document.getElementById("update-btn");
  if (button) button.disabled = true;
  showUpdateBox(
    "Opdaterer programmet",
    "Vent. Browseren finder automatisk programmet igen efter genstarten.",
    "info",
    false
  );
  try {
    const resp = await fetch("/api/update/apply", {
      method: "POST",
      headers: { "X-Update-Token": updateActionToken },
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) throw new Error(data.error || data.detail || "Opdateringen kunne ikke startes.");
    if (!data.restarting) {
      showUpdateBox("Programmet er opdateret", data.message, "success", false);
      return;
    }
    await waitForUpdatedServer(data.instance_id || serverInstanceId);
  } catch (err) {
    showUpdateBox("Opdateringen kunne ikke startes", err.message, "error", true);
  }
}
