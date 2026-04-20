import { PerfBar } from "../components/PerfBar.js";
import { EventRow } from "../components/EventRow.js";
import { DispatchChart } from "../components/DispatchChart.js";

const { h, ref, onMounted, watch } = Vue;

export const DeviceDetail = {
  components: { PerfBar, EventRow, DispatchChart },
  props: { api: { type: Object, required: true }, deviceId: { type: String, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const data = ref(null);

    async function load() {
      try {
        data.value = await props.api.deviceSummary(props.deviceId, { window_days: 30, recent_limit: 20 });
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch(() => props.deviceId, load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading device…");
      if (state.value.err) return h("div", { class: "panel error-text" }, state.value.err);

      const d = data.value;
      const labels = d.recent_events.slice().reverse().map((e) => new Date(e.start_utc).toLocaleDateString());
      const perf = d.recent_events.slice().reverse().map((e) => e.performance_pct);

      return h("div", null, [
        h("div", { class: "crumb" }, [
          h("a", { href: "#/" }, "Dashboard"), " › ",
          h("span", null, d.device_id_external),
        ]),
        h("div", { class: "panel hero-banner" }, [
          h("div", { style: { fontSize: "1.1rem", fontWeight: 600 } },
            `${d.device_id_external} · ${d.primary_pnode_name || d.primary_pnode_id}`),
          h("div", { class: "muted" },
            `listed ${d.listed_capacity_kw || "-"} kW · zone ${d.zone_id || "-"} · window ${d.window_start} to ${d.window_end}`),
        ]),
        h("div", { class: "grid-4" }, [
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Events"),
            h("div", { class: "val" }, d.event_count),
            h("div", { class: "sub" }, `${d.total_dispatch_hours} dispatch hrs`),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Avg performance"),
            h("div", { class: "val" }, d.avg_performance_pct != null ? `${d.avg_performance_pct.toFixed(0)}%` : "-"),
            h("div", { class: "sub" }, d.rank_in_fleet != null ? `rank ${d.rank_in_fleet}` : ""),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Mandatory performance"),
            h("div", { class: "val" }, d.mandatory_performance_pct != null ? `${d.mandatory_performance_pct.toFixed(0)}%` : "-"),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Realized energy"),
            h("div", { class: "val" }, `${d.total_realized_energy_mwh.toFixed(1)} MWh`),
          ]),
        ]),
        h(DispatchChart, {
          labels,
          datasets: [{ label: "Performance % per event", data: perf, color: "#0BD4FF", kind: "line" }],
        }),
        h("div", { class: "panel" }, [
          h("h3", { style: { marginTop: 0 } }, "Recent events"),
          h("table", null, [
            h("thead", null, h("tr", null, ["Event", "Start", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"].map((t) => h("th", null, t)))),
            h("tbody", null, d.recent_events.map((ev) => h(EventRow, { ev, showZone: false }))),
          ]),
        ]),
      ]);
    };
  },
};
