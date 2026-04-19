import { PerfBar } from "./PerfBar.js";
const { h } = Vue;

function fmtEPT(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      timeZone: "America/New_York",
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export const EventRow = {
  components: { PerfBar },
  props: { ev: { type: Object, required: true }, showZone: { type: Boolean, default: true } },
  render() {
    const ev = this.ev;
    return h("tr", { onClick: () => (window.location.hash = `#/events/${encodeURIComponent(ev.event_id)}`) }, [
      h("td", null, ev.event_id),
      h("td", null, fmtEPT(ev.start_utc) + ` · ${ev.duration_hours}h`),
      this.showZone ? h("td", null, ev.zone_id || "—") : null,
      h("td", null, ev.primary_pnode_name || ev.primary_pnode_id),
      h("td", null, ev.has_mandatory
        ? h("span", { class: "pill mand" }, `${ev.extreme_hours}h mand`)
        : h("span", { class: "pill opt" }, `${ev.stressed_hours}h opt`)),
      h("td", null, ev.listed_capacity_kw_avg ? `${(ev.listed_capacity_kw_avg).toFixed(0)} kW` : "—"),
      h("td", null, ev.realized_capacity_kw_avg ? `${(ev.realized_capacity_kw_avg).toFixed(0)} kW` : "—"),
      h("td", null, h(PerfBar, { pct: ev.performance_pct })),
    ].filter(Boolean));
  },
};
