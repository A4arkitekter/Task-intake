import { api, json } from "./api.js";

const next = () => new URLSearchParams(location.search).get("next") || "/";

export function renderLogin(root) {
  document.title = "Log ind · Indtagelse";
  document.body.classList.remove("capture-mode");
  root.innerHTML = `
    <div class="login-wrap">
      <form class="login-card" id="login-form">
        <h1>Indtagelse</h1>
        <p>Kun til dig. Samme kode på telefon og computer.</p>
        <input type="password" name="password" placeholder="Adgangskode" autocomplete="current-password" required />
        <div class="err" id="login-err"></div>
        <button class="primary" type="submit">Log ind</button>
      </form>
    </div>
  `;
  const form = root.querySelector("#login-form");
  const err = root.querySelector("#login-err");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    err.textContent = "";
    const password = new FormData(form).get("password");
    try {
      await json("/api/login", "POST", { password });
      location.href = next();
    } catch (error) {
      err.textContent = error.message;
    }
  });
}

export async function ensureAuth() {
  const me = await api("/api/me");
  if (!me.authenticated) {
    location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    return null;
  }
  return me;
}
