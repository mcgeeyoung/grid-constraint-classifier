// Admin API client. Tenant id is inferred from the first URL path segment,
// e.g. /dominion/ -> "dominion", /pge/ -> "pge". All requests go to
// /api/v1/{utility_id}/admin/*. A window override is still supported for
// local testing.
function inferUtilityId() {
  if (typeof window !== "undefined" && window.__UTILITY_ID__) {
    return String(window.__UTILITY_ID__);
  }
  if (typeof window !== "undefined") {
    const seg = (window.location.pathname || "/").split("/").filter(Boolean)[0];
    if (seg) return seg;
  }
  return "dominion";
}

export const UTILITY_ID = inferUtilityId();

const DEFAULT_BASE = `/api/v1/${UTILITY_ID}/admin`;

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
  uiConfig:           ()                  => apiJson("/ui-config"),
  zones:              ()                  => apiJson("/zones"),
  dashboardToday:     ()                  => apiJson("/dashboard/today"),
  events:             (params = {})       => apiJson("/events" + toQuery(params)),
  eventDetail:        (id)                => apiJson(`/events/${encodeURIComponent(id)}`),
  participation:      (params = {})       => apiJson("/dispatch/participation" + toQuery(params)),
  congestionHeatmap:  (params = {})       => apiJson("/dispatch/congestion-heatmap" + toQuery(params)),
};
