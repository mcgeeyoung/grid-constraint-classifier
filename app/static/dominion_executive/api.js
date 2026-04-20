// Admin API client, mirrored from /dominion-admin/. Same base, same endpoints.
const DEFAULT_BASE = "/api/v1/dominion/admin";

export function apiBase() {
  if (typeof window !== "undefined" && window.__DOMINION_ADMIN_API_BASE__) {
    return String(window.__DOMINION_ADMIN_API_BASE__).replace(/\/$/, "");
  }
  return DEFAULT_BASE;
}

export async function apiJson(path, opts = {}) {
  const res = await fetch(apiBase() + path, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && typeof data === "object" && data.detail ? JSON.stringify(data.detail) : text;
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return data;
}

function toQuery(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

export const api = {
  zones:              ()                  => apiJson("/zones"),
  dashboardToday:     ()                  => apiJson("/dashboard/today"),
  events:             (params = {})       => apiJson("/events" + toQuery(params)),
  eventDetail:        (id)                => apiJson(`/events/${encodeURIComponent(id)}`),
  participation:      (params = {})       => apiJson("/dispatch/participation" + toQuery(params)),
  congestionHeatmap:  (params = {})       => apiJson("/dispatch/congestion-heatmap" + toQuery(params)),
};
