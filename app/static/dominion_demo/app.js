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
  const tiers = sorted.map((r) => (r.period_tier || "normal").toLowerCase());
  // Period-tier shading: full-width vertical bar behind the price line, 1.0 on a
  // hidden 0-1 axis so the band fills the plot height. Stressed = honeydew yellow
  // (optional), extreme = red (mandatory).
  const extremeBars = tiers.map((t) => (t === "extreme" ? 1 : null));
  const stressedBars = tiers.map((t) => (t === "stressed" ? 1 : null));

  const ctx = el("chart-dispatch").getContext("2d");
  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Mandatory (extreme)",
          data: extremeBars,
          backgroundColor: "rgba(229, 83, 75, 0.35)",
          borderWidth: 0,
          yAxisID: "yBar",
          order: 2,
          categoryPercentage: 1.0,
          barPercentage: 1.0,
        },
        {
          type: "bar",
          label: "Optional (stressed)",
          data: stressedBars,
          backgroundColor: "rgba(228, 253, 127, 0.28)",
          borderWidth: 0,
          yAxisID: "yBar",
          order: 2,
          categoryPercentage: 1.0,
          barPercentage: 1.0,
        },
        {
          type: "line",
          label: "Resolved DA congestion ($/MWh)",
          data: resolved,
          borderColor: "#0BD4FF",
          backgroundColor: "rgba(11, 212, 255, 0.1)",
          tension: 0.15,
          spanGaps: true,
          pointRadius: 2,
          yAxisID: "y",
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        title: { display: true, text: oneDevice ? `Device ${oneDevice}` : "Dispatch series", color: "#F1FDFF" },
        legend: { labels: { color: "#F1FDFF" } },
        tooltip: {
          filter: (item) => item.dataset.type !== "bar",
        },
      },
      scales: {
        x: {
          stacked: true,
          ticks: { color: "#6C8C93", maxRotation: 45, minRotation: 0 },
          grid: { display: false },
        },
        y: {
          position: "left",
          ticks: { color: "#6C8C93" },
          grid: { color: "rgba(11, 212, 255, 0.08)" },
          title: { display: true, text: "$/MWh", color: "#6C8C93" },
        },
        yBar: {
          position: "right",
          display: false,
          min: 0,
          max: 1,
          stacked: true,
        },
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
  const window_days = parseInt(el("part-window")?.value || "30", 10);
  el("map-link").href =
    `${API}/asset-map?as_of=${encodeURIComponent(asOf)}&window_days=${window_days}`;
}

function addCell(tr, text, opts = {}) {
  const td = document.createElement("td");
  if (opts.strong) {
    const s = document.createElement("strong");
    s.textContent = text;
    td.appendChild(s);
    if (opts.suffix) td.appendChild(document.createTextNode(opts.suffix));
  } else {
    td.textContent = text;
  }
  if (opts.className) td.className = opts.className;
  tr.appendChild(td);
  return td;
}

async function loadParticipation() {
  const window_days = parseInt(el("part-window").value || "30", 10);
  const asOf = el("map-asof").value || todayISODate();
  const tbody = el("participation-body");
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  const loading = document.createElement("tr");
  const ld = document.createElement("td");
  ld.colSpan = 8;
  ld.className = "muted";
  ld.textContent = "Loading…";
  loading.appendChild(ld);
  tbody.appendChild(loading);

  try {
    const data = await apiJson(
      `/dispatch/participation?window_days=${window_days}&as_of=${encodeURIComponent(asOf)}`
    );
    const label = el("part-window-label");
    label.textContent =
      data.window_start && data.window_end
        ? `${data.window_start} → ${data.window_end} (${data.runs} DA days with data)`
        : "no dispatch data in window";
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (!data.devices.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 8;
      td.className = "muted";
      td.textContent = "No active devices for this as-of date.";
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    const pct = (v) => (v == null ? "—" : ` (${Number(v).toFixed(1)}%)`);
    for (const r of data.devices) {
      const tr = document.createElement("tr");
      const pnode = r.primary_pnode_name
        ? `${r.primary_pnode_name} (${r.primary_pnode_id})`
        : r.primary_pnode_id || "—";
      addCell(tr, r.device_id_external);
      addCell(tr, pnode);
      addCell(tr, String(r.runs));
      addCell(tr, String(r.total_hours));
      addCell(tr, String(r.any_dispatch_hours), {
        strong: true,
        suffix: pct(r.participation_pct),
      });
      addCell(tr, `${r.mandatory_hours}${pct(r.mandatory_pct)}`);
      addCell(tr, String(r.stressed_hours));
      addCell(tr, String(r.normal_hours));
      tbody.appendChild(tr);
    }
  } catch (e) {
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.className = "muted";
    td.textContent = `Error: ${String(e.message || e)}`;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
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
  el("map-asof").addEventListener("change", () => {
    updateMapLink();
    loadParticipation().catch((e) => console.error(e));
  });
  el("btn-refresh-participation").addEventListener("click", () =>
    loadParticipation().catch((e) => console.error(e))
  );
  el("part-window").addEventListener("change", updateMapLink);

  loadRuns()
    .then(loadDevices)
    .then(() => loadParticipation())
    .catch((e) => {
      el("ingest-log").textContent = String(e.message || e);
    });
  updateMapLink();
}

init();
