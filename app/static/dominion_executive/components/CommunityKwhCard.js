const { h } = Vue;

export const CommunityKwhCard = {
  props: {
    participation7: { type: Object, required: true },
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
    return h("div", null, [
      h("div", { class: "h" }, "Community energy delivered · last 7 days"),
      h("div", { class: "v" }, `${Math.round(kwh).toLocaleString()} kWh`),
      h("div", { class: "sub" }, `${devices.length} enrolled pilot devices across Northern Virginia`),
    ]);
  },
};
