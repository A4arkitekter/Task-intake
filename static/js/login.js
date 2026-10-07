import { api } from "./api.js?v=11";

export async function ensureAuth() {
  return api("/api/me");
}
