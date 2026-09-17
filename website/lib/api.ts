// Env-driven, same rule as the backend's config.py: no domain is ever
// hardcoded here. Defaults to localhost so a missing env var in a real
// deployment fails loudly (obviously-broken links) rather than silently
// pointing at a guessed production domain that isn't owned yet.
export const API_URL =
  process.env.NEXT_PUBLIC_NITE_DSP_API_URL ?? "/api";

export async function apiFetch(path: string, init?: RequestInit) {
  return fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
}
