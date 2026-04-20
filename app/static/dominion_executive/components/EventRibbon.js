const { h } = Vue;

function dayKey(isoLike) {
  return String(isoLike).slice(0, 10);
}

export const EventRibbon = {
  props: { events30: { type: Array, required: true } },
  setup(props) {
    return () => {
      // Group events by operating_date. Per day we need:
      //   dispatchHours: sum of stressed_hours + extreme_hours across events that day
      //   hasMandatory: any event that day had has_mandatory === true
      const byDay = new Map();
      for (const ev of props.events30 || []) {
        const k = dayKey(ev.operating_date);
        const cur = byDay.get(k) || { hours: 0, mand: false };
        cur.hours += (ev.stressed_hours || 0) + (ev.extreme_hours || 0);
        if (ev.has_mandatory) cur.mand = true;
        byDay.set(k, cur);
      }

      // Build the last 30 UTC days ending today.
      const days = [];
      const today = new Date();
      for (let i = 29; i >= 0; i--) {
        const d = new Date(today);
        d.setUTCDate(today.getUTCDate() - i);
        const k = d.toISOString().slice(0, 10);
        const agg = byDay.get(k) || { hours: 0, mand: false };
        days.push({ key: k, hours: agg.hours, mand: agg.mand });
      }

      const mandatoryDays = days.filter((d) => d.mand).length;
      const stressedDays = days.filter((d) => d.hours > 0).length;
      const calmDays = 30 - stressedDays;
      const maxHours = Math.max(1, ...days.map((d) => d.hours));

      return h("div", null, [
        h("div", { class: "h" }, "Grid stress rhythm · last 30 days"),
        h("div", { class: "pulse-line" }, [
          `The grid stressed on ${stressedDays} of the last 30 days. `,
          h("span", { class: "pulse-line-mand" }, `${mandatoryDays} required mandatory dispatch`),
          ". ",
          h("span", { class: "pulse-line-calm" }, `${calmDays} calm days`),
          ".",
        ]),
        h("div", { class: "pulse-strip" }, days.map((d) => {
          const heightPct = d.hours > 0 ? Math.max(12, (d.hours / maxHours) * 100) : 4;
          const cls = d.mand ? "mand" : d.hours > 0 ? "opt" : "";
          return h("div", {
            class: "pulse-bar-wrap",
            title: `${d.key} · ${d.hours} h${d.mand ? " · mandatory" : d.hours > 0 ? " · optional" : ""}`,
          }, [
            h("div", { class: ["pulse-bar", cls], style: { height: `${heightPct}%` } }),
          ]);
        })),
        h("div", { class: "disc" }, "Bar height is dispatch hours that day. Red bars required mandatory dispatch. Grid stress is a property of the grid itself; does not scale with device count."),
      ]);
    };
  },
};
