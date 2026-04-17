/**
 * Dominion DER demo — calls FastAPI `/api/v1/dominion/*` (or absolute URL from config.js).
 */
function apiBase() {
  if (typeof window !== "undefined" && window.__DOMINION_API_BASE__) {
    return String(window.__DOMINION_API_BASE__).replace(/\/$/, "");
  }
  return "/api/v1/dominion";
}

const API = apiBase();

function todayISODate() {
  const d = new Date();
  const z = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

function el(id) {
  return document.getElementById(id);
}

async function apiJson(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    ...options,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const msg = typeof data === "object" && data && data.detail ? JSON.stringify(data.detail) : text;
    throw new Error(`${res.status} ${res.statusText}: ${msg}`);
  }
  return data;
}

function setLog(id, text) {
  el(id).textContent = text;
}

let chartInstance = null;

function tierCounts(rows) {
  const c = { normal: 0, stressed: 0, extreme: 0, off: 0, other: 0 };
  for (const r of rows) {
    const t = (r.period_tier || "normal").toLowerCase();
    if (c[t] === undefined) c.other += 1;
    else c[t] += 1;
  }
  return c;
}

function renderChart(rows, deviceId) {
  const filtered = deviceId ? rows.filter((r) => r.device_id_external === deviceId) : rows;
  const oneDevice = deviceId || (filtered[0] && filtered[0].device_id_external);
  const series = oneDevice ? filtered.filter((r) => r.device_id_external === oneDevice) : filtered;
  const sorted = [...series].sort((a, b) => new Date(a.interval_start_utc) - new Date(b.interval_start_utc));

  const labels = sorted.map((r) => {
    const d = new Date(r.interval_start_utc);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  });
  const resolved = sorted.map((r) => (r.resolved_congestion == null ? null : Number(r.resolved_congestion)));
  const program = sorted.map((r) => (r.dispatch_signal_program == null ? null : Number(r.dispatch_signal_program)));

  const ctx = el("chart-dispatch").getContext("2d");
  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Resolved DA congestion ($/MWh)",
          data: resolved,
          borderColor: "#79c0ff",
          backgroundColor: "rgba(121, 192, 255, 0.1)",
          tension: 0.15,
          spanGaps: true,
        },
        {
          label: "Program dispatch signal",
          data: program,
          borderColor: "#3fb950",
          backgroundColor: "rgba(63, 185, 80, 0.1)",
          tension: 0.15,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        title: { display: true, text: oneDevice ? `Device ${oneDevice}` : "Dispatch series" },
        legend: { labels: { color: "#c9d1d9" } },
      },
      scales: {
        x: { ticks: { color: "#8b98a5", maxRotation: 45, minRotation: 0 } },
        y: { ticks: { color: "#8b98a5" }, grid: { color: "#2d3844" } },
      },
    },
  });
}

async function loadRuns() {
  const runs = await apiJson("/ingestion-runs?limit=50");
  const tbody = el("runs-body");
  tbody.innerHTML = "";
  for (const r of runs) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="click-run" data-id="${r.id}">${r.id}</td><td>${r.operating_date}</td><td>${r.status}</td><td>${r.row_count ?? "—"}</td>`;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll(".click-run").forEach((cell) => {
    cell.addEventListener("click", () => {
      el("run-id").value = cell.dataset.id;
      el("ingest-date").value = cell.closest("tr").children[1].textContent;
      el("map-asof").value = cell.closest("tr").children[1].textContent;
      updateMapLink();
    });
  });
  if (runs.length && !el("run-id").value) el("run-id").value = runs[0].id;
  if (runs.length && !el("ingest-date").value) el("ingest-date").value = runs[0].operating_date;
  if (runs.length && !el("map-asof").value) el("map-asof").value = runs[0].operating_date;
  updateMapLink();
}

async function loadDevices() {
  const asOf = el("map-asof").value || todayISODate();
  const devices = await apiJson(`/devices?as_of=${encodeURIComponent(asOf)}`);
  const tbody = el("devices-body");
  tbody.innerHTML = "";
  const sel = el("device-select");
  sel.innerHTML = '<option value="">All devices (chart uses first)</option>';
  for (const d of devices) {
    const tr = document.createElement("tr");
    const asset = d.asset_display_name || (d.asset_lat != null ? `${d.asset_lat}, ${d.asset_lon}` : "—");
    tr.innerHTML = `<td>${d.device_id_external}</td><td>${d.primary_pnode_id}</td><td>${asset}</td>`;
    tbody.appendChild(tr);
    const opt = document.createElement("option");
    opt.value = d.device_id_external;
    opt.textContent = d.device_id_external;
    sel.appendChild(opt);
  }
}

function updateMapLink() {
  const asOf = el("map-asof").value || todayISODate();
  el("map-link").href = `${API}/asset-map?as_of=${encodeURIComponent(asOf)}`;
}

async function doIngest() {
  const operating_date = el("ingest-date").value;
  if (!operating_date) {
    setLog("ingest-log", "Pick a date.");
    return;
  }
  setLog("ingest-log", "Requesting…");
  try {
    const body = {
      operating_date,
      replace_existing: el("ingest-replace").checked,
      zone_code: "DOM",
      lmp_type: "LOAD",
    };
    const run = await apiJson("/ingest", { method: "POST", body: JSON.stringify(body) });
    setLog("ingest-log", JSON.stringify(run, null, 2));
    await loadRuns();
    await loadDevices().catch(() => {});
    el("run-id").value = run.id;
  } catch (e) {
    setLog("ingest-log", String(e.message || e));
  }
}

async function doRebuild() {
  const ingestion_run_id = parseInt(el("run-id").value, 10);
  if (!ingestion_run_id) {
    setLog("dispatch-log", "Set ingestion run id.");
    return;
  }
  setLog("dispatch-log", "Rebuilding…");
  try {
    const body = {
      ingestion_run_id,
      replace_existing: true,
      no_period_policy: el("policy-off").checked,
      stressed_threshold_usd: 2,
      extreme_quantile: 0.95,
      stressed_signal_fraction: 0.5,
      stressed_peak_only: el("stressed-peak-only").checked,
    };
    const out = await apiJson("/dispatch/rebuild", { method: "POST", body: JSON.stringify(body) });
    setLog("dispatch-log", JSON.stringify(out, null, 2));
  } catch (e) {
    setLog("dispatch-log", String(e.message || e));
  }
}

async function doLoadDispatch() {
  const ingestion_run_id = parseInt(el("run-id").value, 10);
  if (!ingestion_run_id) {
    setLog("dispatch-log", "Set ingestion run id.");
    return;
  }
  const dev = el("device-select").value;
  const q = dev
    ? `?ingestion_run_id=${ingestion_run_id}&device_id_external=${encodeURIComponent(dev)}`
    : `?ingestion_run_id=${ingestion_run_id}`;
  setLog("dispatch-log", "Loading…");
  try {
    const rows = await apiJson(`/dispatch${q}`);
    const tc = tierCounts(rows);
    el("tier-summary").innerHTML = `<span>normal: <strong>${tc.normal}</strong></span>
      <span>stressed: <strong>${tc.stressed}</strong></span>
      <span>extreme: <strong>${tc.extreme}</strong></span>
      <span>mandatory hours: <strong>${rows.filter((r) => r.dispatch_mandatory).length}</strong></span>`;
    renderChart(rows, dev);
    setLog("dispatch-log", `Loaded ${rows.length} rows.`);
  } catch (e) {
    setLog("dispatch-log", String(e.message || e));
  }
}

function init() {
  const remote = typeof window !== "undefined" && window.__DOMINION_API_BASE__;
  if (remote) {
    const only = document.getElementById("intro-local-only");
    if (only) only.style.display = "none";
    const foot = document.getElementById("api-footer");
    if (foot) foot.innerHTML = `API: <code>${remote}</code>`;
  }

  el("ingest-date").value = todayISODate();
  el("map-asof").value = todayISODate();

  el("btn-ingest").addEventListener("click", doIngest);
  el("btn-refresh-runs").addEventListener("click", () => loadRuns().catch((e) => console.error(e)));
  el("btn-rebuild").addEventListener("click", doRebuild);
  el("btn-load-dispatch").addEventListener("click", doLoadDispatch);
  el("btn-refresh-devices").addEventListener("click", () => loadDevices().catch((e) => console.error(e)));
  el("map-asof").addEventListener("change", updateMapLink);

  loadRuns()
    .then(loadDevices)
    .catch((e) => {
      el("ingest-log").textContent = String(e.message || e);
    });
  updateMapLink();
}

init();
