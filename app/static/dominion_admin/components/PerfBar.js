const { h } = Vue;

export const PerfBar = {
  props: { pct: { type: [Number, null], default: null } },
  render() {
    const pct = this.pct == null ? null : Math.max(0, Math.min(100, this.pct));
    const cls = pct == null ? "" : pct >= 90 ? "" : pct >= 75 ? "warn" : "bad";
    return h("span", { class: "perfbar" }, [
      h("span", { class: "track" }, [
        h("span", {
          class: `fill ${cls}`,
          style: { width: pct == null ? "0%" : `${pct}%` },
        }),
      ]),
      h("span",
        { class: pct == null ? "muted" : `v-${cls || "green"}`, style: { minWidth: "3rem", textAlign: "right" } },
        pct == null ? "-" : `${pct.toFixed(0)}%`),
    ]);
  },
};
