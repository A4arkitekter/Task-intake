import { api } from "./api.js?v=14";

export async function ensureAuth() {
  return api("/api/me");
}
