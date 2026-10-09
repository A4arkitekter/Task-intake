import { api } from "./api.js?v=13";

export async function ensureAuth() {
  return api("/api/me");
}
