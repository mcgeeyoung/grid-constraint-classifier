const { h } = Vue;

// Settlement rate: DOM zone p85 abs congestion over trailing 365 DA days.
// Computed once offline (see spec §5.4). Hardcoded here to avoid an extra
// round-trip; re-derive if the backfill window changes materially.
const DOM_P85_USD_PER_MWH = 16.60;

export const RatepayerValueCard = {
  props: {
    participation30: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    const devices = this.participation30?.devices || [];
    // Same kWh estimate as CommunityKwhCard but over 30 days.
    let baseKwh = 0;
    for (const d of devices) {
      baseKwh += (d.any_dispatch_hours || 0) * 0.85 * 700;
    }
    const scaledKwh = baseKwh * this.scaleFactor;
    const dollars = scaledKwh * 0.001 * DOM_P85_USD_PER_MWH;
    return h("div", null, [
      h("div", { class: "h" }, "Value returned to Virginia ratepayers · last 30 days"),
      h("div", { class: "v honey" }, `$${Math.round(dollars).toLocaleString()}`),
      h("div", { class: "sub" }, "Participation payments · stays in Virginia counties"),
      h("div", { class: "disc" }, "Computed at DOM zone p85 congestion ($16.60/MWh, trailing 365 DA days)."),
    ]);
  },
};
