const { h } = Vue;

// Fallback if the SPA renders before ui-config lands (should not happen but
// keeps the component honest). Mirrors the Dominion figure.
const FALLBACK_RATE_USD_PER_MWH = 16.60;
const FALLBACK_RATE_DESCRIPTION =
  "Computed at DOM zone p85 congestion ($16.60/MWh, trailing 365 DA days).";

// Map short geo phrase -> ratepayer headline region. Keeps the copy natural
// ("Virginia ratepayers", "California ratepayers") without another config
// field. Falls back to "local ratepayers" when the phrase isn't recognized.
function ratepayerRegion(subLocation) {
  const s = String(subLocation || "");
  const m = s.match(/(Virginia|California|Maryland|New York|Pennsylvania|Illinois|Texas|Ohio|Michigan|New Jersey)\b/);
  return m ? m[1] : "local";
}

export const RatepayerValueCard = {
  props: {
    participation30: { type: Object, required: true },
    // Settlement rate from ui-config; falls back to the Dominion baseline.
    settlementRateUsdPerMwh: { type: Number, default: FALLBACK_RATE_USD_PER_MWH },
    // Full disclosure line from ui-config; falls back to the Dominion baseline.
    settlementRateDescription: { type: String, default: FALLBACK_RATE_DESCRIPTION },
    // Short geo phrase, e.g. "Northern Virginia".
    subLocation: { type: String, default: "" },
  },
  render() {
    const devices = this.participation30?.devices || [];
    // Same kWh estimate as CommunityKwhCard but over 30 days.
    let kwh = 0;
    for (const d of devices) {
      kwh += (d.any_dispatch_hours || 0) * 0.85 * 700;
    }
    const rate = Number(this.settlementRateUsdPerMwh) || FALLBACK_RATE_USD_PER_MWH;
    const dollars = kwh * 0.001 * rate;
    const region = ratepayerRegion(this.subLocation);
    const subCopy = region === "local"
      ? "Participation payments · stays local"
      : `Participation payments · stays in ${region} counties`;
    return h("div", null, [
      h("div", { class: "h" }, `Value returned to ${region} ratepayers · last 30 days`),
      h("div", { class: "v honey" }, `$${Math.round(dollars).toLocaleString()}`),
      h("div", { class: "sub" }, subCopy),
      h("div", { class: "disc" }, this.settlementRateDescription || FALLBACK_RATE_DESCRIPTION),
    ]);
  },
};
