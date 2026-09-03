const API_JSON = { "Content-Type": "application/json" };

export async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: { ...(options.headers || {}) },
  });
  if (response.status === 401 && path !== "/api/login") {
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = `/login?next=${next}`;
    throw new Error("auth");
  }
  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!response.ok) {
    throw new Error((data && data.detail) || "Noget gik galt");
  }
  return data;
}

export function json(path, method, body) {
  return api(path, {
    method,
    headers: API_JSON,
    body: JSON.stringify(body || {}),
  });
}

export function formatWhen(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("da-DK", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    day: "numeric",
    month: "short",
  }).format(date);
}
