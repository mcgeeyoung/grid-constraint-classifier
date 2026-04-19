const { h } = Vue;

export const ZoneCard = {
  props: { zone: { type: Object, required: true }, slice: { type: Object, default: () => ({}) }, lastPerf: { type: [Number, null], default: null } },
  render() {
    const z = this.zone;
    const sl = this.slice || {};
    const peakMw = (sl.peak_kw || 0) / 1000;
    const listedMw = (z.listed_capacity_kw || 0) / 1000;
    return h("div", { class: "panel" }, [
      h("div", { class: "kpi" }, [
        h("div", { class: "label" }, z.label),
        h("div", { class: "val" }, `${listedMw.toFixed(1)} MW`),
        h("div", { class: "sub" },
          `${z.device_count} devices · ${sl.events || 0} events fcst · peak ${peakMw.toFixed(1)} MW`),
        this.lastPerf != null
          ? h("div", { class: "sub" }, `last event perf ${this.lastPerf.toFixed(0)}%`)
          : null,
      ]),
    ]);
  },
};
