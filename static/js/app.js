import { renderInbox } from "./inbox.js?v=18";
import { renderCapture } from "./capture.js?v=18";
import { ensureAuth } from "./login.js?v=18";

const root = document.querySelector("#app");

function route() {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/ny-ide") {
    return ensureAuth().then((me) => {
      if (me) renderCapture(root, me);
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
  navigator.serviceWorker.getRegistrations()
    .then((regs) => Promise.all(regs.map((reg) => reg.unregister())))
    .then(() => caches.keys())
    .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
    .then(() => navigator.serviceWorker.register("/sw.js?v=18"))
    .catch(() => {});
}
