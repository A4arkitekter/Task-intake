import { api } from "./api.js";

export async function ensureAuth() {
  return api("/api/me");
}
