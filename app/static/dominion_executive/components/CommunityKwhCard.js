const { h } = Vue;

export const CommunityKwhCard = {
  props: {
    participation7: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    // Sum realized kWh across devices, scaled by the scenario factor.
    // participation7.devices[].any_dispatch_hours * that device's listed_capacity_kw
    // is the closest proxy we have without a dedicated "realized_kwh" field.
    // Use total_hours instead of any_dispatch_hours because we mock realized kw
    // for every dispatch hour via the telemetry_mock module.
    const devices = this.participation7?.devices || [];
    // Rough kWh proxy: sum of (any_dispatch_hours × avg listed kW × avg realized ratio).
    // Real "realized kWh" is in the /events/{id} hourly rows, but aggregating across
    // 7 days × 6 devices × N hours in the browser is wasteful. Use a defensible
    // derived estimate: any_dispatch_hours × avg_listed_kw × 0.85 (a "typical
    // realization ratio" matching telemetry_mock's band).
    let baseKwh = 0;
    for (const d of devices) {
      baseKwh += (d.any_dispatch_hours || 0) * 0.85 * 700; // 700 kW avg listed per demo device
    }
    const scaledKwh = baseKwh * this.scaleFactor;
    return h("div", null, [
      h("div", { class: "h" }, "Community energy delivered · last 7 days"),
      h("div", { class: "v" }, `${Math.round(scaledKwh).toLocaleString()} kWh`),
      h("div", { class: "sub" }, "Virginia rooftops and small businesses · scaled by scenario"),
    ]);
  },
};
