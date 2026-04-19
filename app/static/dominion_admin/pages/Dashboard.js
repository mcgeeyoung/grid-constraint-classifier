import { ZoneCard } from "../components/ZoneCard.js";
import { EventRow } from "../components/EventRow.js";
import { DispatchChart } from "../components/DispatchChart.js";
import { ZoneMap } from "../components/ZoneMap.js";

const { h, ref, onMounted } = Vue;

export const Dashboard = {
  components: { ZoneCard, EventRow, DispatchChart, ZoneMap },
  props: { api: { type: Object, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const today = ref(null);
    const zones = ref([]);
    const recent = ref([]);

    async function load() {
      try {
        const [t, z, r] = await Promise.all([
          props.api.dashboardToday(),
          props.api.zones(),
          props.api.events({ window_days: 30, limit: 6 }),
        ]);
        today.value = t;
        zones.value = z;
        recent.value = r.events;
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading dashboard…");
      if (state.value.err) return h("div", { class: "panel", style: { color: "#e5534b" } }, state.value.err);

      const t = today.value;
      const labels = t.fleet_24h_signal.map((x) => new Date(x.hour_utc).toLocaleTimeString(undefined, { timeZone: "America/New_York", hour: "2-digit" }));
      const sig = t.fleet_24h_signal.map((x) => x.program_signal);

      return h("div", null, [
        h("div", { class: "panel hero-banner" }, [
          h("div", { class: "label", style: { color: "#8b98a5" } }, `Operating ${t.operating_date} · ${t.forecast_basis === "tomorrow_da" ? "PJM DA (tomorrow)" : "most recent DA"}`),
          h("div", { style: { fontSize: "1.3rem", fontWeight: 600 } },
            `${t.events_forecast} events forecast · peak ${(t.peak_program_kw / 1000).toFixed(1)} MW`),
        ]),
        h("div", { class: "grid-3" }, zones.value.map((z) => h(ZoneCard, {
          zone: z,
          slice: (t.by_zone || []).find((s) => s.zone_id === z.id) || {},
        }))),
        h("div", { class: "grid-2-1" }, [
          h(DispatchChart, {
            labels,
            datasets: [{ label: "Fleet program signal (avg)", data: sig, color: "#3fb950", kind: "line" }],
          }),
          h(ZoneMap, {
            devices: zones.value.flatMap((z) => z.device_ids.map((d) => ({ device_id_external: d, zone_id: z.id }))),
            minHeight: "18rem",
          }),
        ]),
        h("div", { class: "panel" }, [
          h("h3", { style: { marginTop: 0 } }, "Recent events"),
          h("table", null, [
            h("thead", null, h("tr", null, [
              ["Event", "Start", "Zone", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"]
                .map((t) => h("th", null, t)),
            ])),
            h("tbody", null, recent.value.map((ev) => h(EventRow, { ev }))),
          ]),
        ]),
      ]);
    };
  },
};
