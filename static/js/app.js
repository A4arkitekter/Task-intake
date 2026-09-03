import { renderInbox } from "./inbox.js";
import { renderCapture } from "./capture.js";
import { renderLogin, ensureAuth } from "./login.js";

const root = document.querySelector("#app");

function route() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/login") return renderLogin(root);
  if (path === "/ny-ide") {
    return ensureAuth().then((me) => {
      if (me) renderCapture(root);
    });
  }
  return renderInbox(root);
}

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[href]");
  if (!link) return;
  const url = new URL(link.href, location.origin);
  if (url.origin !== location.origin) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || link.target === "_blank") return;
  event.preventDefault();
  history.pushState({}, "", url.pathname + url.search);
  route();
});

window.addEventListener("popstate", route);
route();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
