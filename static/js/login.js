import { api } from "./api.js?v=18";

export async function ensureAuth() {
  return api("/api/me");
}
