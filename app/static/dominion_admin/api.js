// Thin fetch wrapper for the Dominion admin API.
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

export const api = {
  zones:           ()                       => apiJson("/zones"),
  zone:            (zoneId)                 => apiJson(`/zones/${encodeURIComponent(zoneId)}`),
  dashboardToday:  ()                       => apiJson("/dashboard/today"),
  events:          (params = {})            => apiJson("/events" + toQuery(params)),
  eventDetail:     (id)                     => apiJson(`/events/${encodeURIComponent(id)}`),
  deviceSummary:   (id, params = {})        => apiJson(`/devices/${encodeURIComponent(id)}/summary` + toQuery(params)),
};

function toQuery(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}
