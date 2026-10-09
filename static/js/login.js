import { api } from "./api.js?v=16";

export async function ensureAuth() {
  return api("/api/me");
}
