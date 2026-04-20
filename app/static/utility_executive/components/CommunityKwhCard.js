const { h } = Vue;

export const CommunityKwhCard = {
  props: {
    participation7: { type: Object, required: true },
    // Count of enrolled pilot pnodes (from ui-config). Falls back to the
    // device count from the participation rollup if the prop is empty.
    pilotPnodes: { type: Array, default: () => [] },
    // Short geo phrase, e.g. "Northern Virginia" or "Northern California".
    subLocation: { type: String, default: "" },
  },
  render() {
    // Realized kWh proxy across the enrolled pilot devices over 7 DA days:
    //   any_dispatch_hours × 0.85 realization ratio × 700 kW avg listed.
    // Real realized kWh lives in /events/{id} hourly rows; aggregating client-
    // side is wasteful. The proxy matches telemetry_mock's band.
    const devices = this.participation7?.devices || [];
    let kwh = 0;
    for (const d of devices) {
      kwh += (d.any_dispatch_hours || 0) * 0.85 * 700;
    }
    const pilotCount = (this.pilotPnodes && this.pilotPnodes.length) || devices.length;
    const loc = this.subLocation || "the service territory";
    return h("div", null, [
      h("div", { class: "h" }, "Community energy delivered · last 7 days"),
      h("div", { class: "v" }, `${Math.round(kwh).toLocaleString()} kWh`),
      h("div", { class: "sub" }, `${pilotCount} enrolled pilot devices across ${loc}`),
    ]);
  },
};
