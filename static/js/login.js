import { api } from "./api.js?v=19";

export async function ensureAuth() {
  return api("/api/me");
}
