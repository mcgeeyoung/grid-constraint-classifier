import { PerfBar } from "../components/PerfBar.js";
import { DispatchChart } from "../components/DispatchChart.js";
import { ZoneMap } from "../components/ZoneMap.js";

const { h, ref, onMounted, watch } = Vue;

function fmt(v, fn, fallback = "-") {
  return v == null ? fallback : fn(v);
}

export const EventDetail = {
  components: { PerfBar, DispatchChart, ZoneMap },
  props: { api: { type: Object, required: true }, eventId: { type: String, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const ev = ref(null);

    async function load() {
      try {
        ev.value = await props.api.eventDetail(props.eventId);
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch(() => props.eventId, load);

    return () => {
      if (state.value.loading) return h("div", { class: "loading" }, "Loading event…");
      if (state.value.err) return h("div", { class: "panel error-text" }, state.value.err);

      const e = ev.value;
      const labels = e.hours.map((h) => {
        const d = new Date(h.interval_start_utc);
        return d.toLocaleTimeString(undefined, { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" });
      });
      const ds = [
        { label: "Program signal", data: e.hours.map((h) => h.dispatch_signal_program), color: "#0BD4FF", kind: "line" },
        { label: "Listed ask (kW)", data: e.hours.map((h) => h.listed_kw_ask), color: "#C0F5FF", kind: "line" },
        { label: "Realized (kW)",   data: e.hours.map((h) => h.realized_kw), color: "#E4FD7F", kind: "bar" },
      ];

      return h("div", null, [
        h("div", { class: "crumb" }, [
          h("a", { href: "#/" }, "Dashboard"), " › ",
          h("a", { href: "#/history" }, "Events"), " › ",
          h("span", null, e.event_id),
        ]),
        h("div", { class: "panel hero-banner" }, [
          h("div", { style: { fontSize: "1.1rem", fontWeight: 600 } },
            `${e.event_id} · ${e.duration_hours}h · ${e.device_id_external}`),
          h("div", { class: "muted" },
            `Operating ${e.operating_date} · ${e.stressed_hours} stressed + ${e.extreme_hours} mandatory · zone ${e.zone_id || "-"}`),
        ]),
        h("div", { class: "grid-4" }, [
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Listed capacity (avg)"),
            h("div", { class: "val" }, fmt(e.listed_capacity_kw_avg, (v) => `${v.toFixed(0)} kW`)),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Realized capacity (avg)"),
            h("div", { class: "val" }, fmt(e.realized_capacity_kw_avg, (v) => `${v.toFixed(0)} kW`)),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Performance"),
            h("div", { class: "val" }, fmt(e.performance_pct, (v) => `${v.toFixed(1)}%`)),
            h("div", { class: "sub" }, "realized / listed"),
          ]),
          h("div", { class: "panel kpi" }, [
            h("div", { class: "label" }, "Mandatory performance"),
            h("div", { class: "val" }, fmt(e.mandatory_performance_pct, (v) => `${v.toFixed(1)}%`)),
            h("div", { class: "sub" }, "extreme hours only"),
          ]),
        ]),
        h("div", { class: "grid-2-1" }, [
          h(DispatchChart, { labels, datasets: ds, height: 240 }),
          h(ZoneMap, {
            id: "mini-map",
            minHeight: "14rem",
            devices: [{
              device_id_external: e.device_id_external,
              primary_pnode_id: e.primary_pnode_id,
              zone_id: e.zone_id,
              perf_pct: e.performance_pct,
            }],
          }),
        ]),
      ]);
    };
  },
};
