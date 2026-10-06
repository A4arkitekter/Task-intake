import { api, formatWhen } from "./api.js";
import { ensureAuth } from "./login.js";

let poll = null;
let onVisible = null;
let updateActionToken = "";
let serverInstanceId = "";
let updateOutcomeShown = false;
let lastJobsHash = "";
let folderTimer = null;
let assigneeTimer = null;
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
  await initUpdateBanner();
  await loadDashboard(root);
  if (poll) clearInterval(poll);
  poll = setInterval(() => refreshJobs(root), 2500);
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
    <section class="dash-card">
      <h2>Status</h2>
      <div id="lamps" class="lamps">${lampsHtml(data.health || {})}</div>
      <div class="card-actions" style="margin-top:1rem">
        <a class="primary" href="/api/admin/report">Hent fejlrapport.zip</a>
      </div>
      <p class="col-hint">Zip uden token, .env og lyd. Læg den i Cursor, når noget er rødt.</p>
    </section>
    <section class="dash-card">
      <h2>Hvor lander opgaverne</h2>
      <p class="col-hint">Mappe, ansvarlig og prioritet gemmes her — ikke i .env. Token er til hele Wrike, ikke en person.</p>
      <label for="inbox-dir">Mappe med optagelser</label>
      <div class="row-input">
        <input id="inbox-dir" value="${escapeAttr(settings.inbox_dir || "")}" />
        <button class="primary" id="save-inbox" type="button">Gem sti</button>
      </div>
      <label for="folder-search">Wrike-mappe</label>
      <div id="selected-folder" class="selected-folder">${selectedFolderHtml(settings)}</div>
      <input id="folder-search" placeholder="Søg efter mappe…" />
      <div id="folder-results" class="folder-results"></div>
      <label for="assignee-search">Ansvarlig</label>
      <div id="selected-assignee" class="selected-folder">${selectedAssigneeHtml(settings)}</div>
      <input id="assignee-search" placeholder="Søg efter navn eller mail…" />
      <div id="assignee-results" class="folder-results"></div>
      <label for="importance">Prioritet</label>
      <select id="importance">
        <option value="High"${settings.wrike_importance === "High" ? " selected" : ""}>High</option>
        <option value="Normal"${settings.wrike_importance === "Normal" ? " selected" : ""}>Normal</option>
        <option value="Low"${settings.wrike_importance === "Low" ? " selected" : ""}>Low</option>
      </select>
      <div class="card-actions" style="margin-top:1rem">
        <button class="primary" id="test-wrike" type="button">Opret testopgave</button>
      </div>
      <p id="settings-msg" class="muted"></p>
    </section>
    <section class="dash-card">
      <h2>Seneste job</h2>
      <div id="jobs">${jobsHtml(data.jobs || [])}</div>
    </section>
  `;
  lastJobsHash = JSON.stringify({ jobs: data.jobs, health: data.health, waiting: data.waiting });
  bindSettings(root);
  bindJobActions(root);
}

function bindSettings(root) {
  const saveInbox = root.querySelector("#save-inbox");
  const inbox = root.querySelector("#inbox-dir");
  const importance = root.querySelector("#importance");
  const search = root.querySelector("#folder-search");
  const assigneeSearch = root.querySelector("#assignee-search");
  const testBtn = root.querySelector("#test-wrike");
  saveInbox?.addEventListener("click", async () => {
    await saveSettings(root, { inbox_dir: inbox.value });
  });
  importance?.addEventListener("change", async () => {
    await saveSettings(root, { wrike_importance: importance.value });
  });
  search?.addEventListener("input", () => {
    clearTimeout(folderTimer);
    folderTimer = setTimeout(() => searchFolders(root, search.value), 250);
  });
  assigneeSearch?.addEventListener("input", () => {
    clearTimeout(assigneeTimer);
    assigneeTimer = setTimeout(() => searchContacts(root, assigneeSearch.value), 250);
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
      box.innerHTML = `<p class="empty">Ingen mapper matcher.</p>`;
      return;
    }
    box.innerHTML = folders.map((folder) => `
      <button type="button" class="folder-item" data-folder-id="${escapeAttr(folder.id)}" data-folder-title="${escapeAttr(folder.title)}">
        ${escapeHtml(folder.title)}
      </button>
    `).join("");
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

async function searchContacts(root, query) {
  const box = root.querySelector("#assignee-results");
  if (!box) return;
  if (!query.trim()) {
    box.innerHTML = "";
    return;
  }
  try {
    const data = await api(`/api/admin/wrike/contacts?q=${encodeURIComponent(query.trim())}`);
    const contacts = data.contacts || [];
    if (!contacts.length) {
      box.innerHTML = `<p class="empty">Ingen personer matcher.</p>`;
      return;
    }
    box.innerHTML = contacts.map((person) => `
      <button type="button" class="folder-item" data-assignee-id="${escapeAttr(person.id)}" data-assignee-title="${escapeAttr(person.name || person.title)}">
        ${escapeHtml(person.title)}
      </button>
    `).join("");
    box.querySelectorAll("[data-assignee-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        await saveSettings(root, {
          wrike_assignee_id: button.getAttribute("data-assignee-id"),
          wrike_assignee_name: button.getAttribute("data-assignee-title"),
        });
        const search = root.querySelector("#assignee-search");
        if (search) search.value = "";
        box.innerHTML = "";
      });
    });
  } catch (error) {
    box.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

async function refreshJobs(root) {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) return;
  try {
    const data = await api("/api/admin");
    const hash = JSON.stringify({ jobs: data.jobs, health: data.health, waiting: data.waiting });
    if (hash === lastJobsHash) return;
    lastJobsHash = hash;
    const lamps = root.querySelector("#lamps");
    const jobs = root.querySelector("#jobs");
    if (lamps) lamps.innerHTML = lampsHtml(data.health || {});
    if (jobs) {
      jobs.innerHTML = jobsHtml(data.jobs || []);
      bindJobActions(root);
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
        lastJobsHash = "";
        await refreshJobs(root);
      } catch (error) {
        button.disabled = false;
        button.textContent = "Prøv igen";
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
  if (settings.wrike_folder_name || settings.wrike_folder_id) {
    const extra = settings.wrike_folder_defaulted ? " (valgt automatisk — du kan skifte)" : "";
    return `<strong>${escapeHtml(settings.wrike_folder_name || settings.wrike_folder_id)}</strong>${escapeHtml(extra)}`;
  }
  return "Ingen mappe valgt endnu. Søg ovenfor. Første gang vælger programmet selv Indbakke/Inbox, hvis den findes.";
}

function selectedAssigneeHtml(settings) {
  if (settings.wrike_assignee_name || settings.wrike_assignee_id) {
    return `<strong>${escapeHtml(settings.wrike_assignee_name || settings.wrike_assignee_id)}</strong>`;
  }
  return "Ingen ansvarlig valgt endnu. Søg efter navn eller mail.";
}

function jobsHtml(jobs) {
  if (!jobs.length) return `<p class="empty">Ingen job endnu. Tal en idé ind på telefonen.</p>`;
  return `<div class="job-list">${jobs.map(jobRow).join("")}</div>`;
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
  const link = sent?.wrike_url
    ? `<a href="${escapeAttr(sent.wrike_url)}" target="_blank" rel="noopener">Åbn i Wrike</a>`
    : "";
  const retry = failed || pending
    ? `<button class="ghost" data-retry-capture="${job.id}" type="button">Prøv igen</button>`
    : "";
  return `
    <article class="job-row">
      <div>
        <div class="when">${formatWhen(job.created_at)}</div>
        <strong>${escapeHtml(title)}</strong>
        ${job.error_message ? `<div class="sub">${escapeHtml(job.error_message)}</div>` : ""}
      </div>
      <div class="job-meta">
        <span class="status-pill">${escapeHtml(status)}</span>
        ${link}
        ${retry}
      </div>
    </article>
  `;
}

function setSettingsMsg(root, text) {
  const node = root.querySelector("#settings-msg");
  if (node) node.textContent = text || "";
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
