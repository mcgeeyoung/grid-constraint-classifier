const { h } = Vue;

export const HeaderBar = {
  props: {
    today: { type: Object, required: true },
    // Tenant hero lead; falls back to a generic line when absent.
    headlineLead: { type: String, default: "" },
  },
  render() {
    const t = this.today;
    // "DA tomorrow" reads right for any ISO (PJM, CAISO, ...). Keeping it
    // ISO-neutral avoids another per-tenant string.
    const basisLabel = t.forecast_basis === "tomorrow_da" ? "DA tomorrow" : "latest cleared DA";
    const peakMw = (t.peak_program_kw / 1000).toFixed(1);
    const lead = this.headlineLead || "Communities deliver back to the grid.";
    return h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" } }, [
      h("div", { class: "lead" }, lead),
      h("div", { class: "grid-state" }, [
        h("div", { class: "h" }, `${basisLabel} · ${t.operating_date}`),
        h("div", { class: "v" }, `${t.events_forecast} events · ${peakMw} MW peak`),
      ]),
    ]);
  },
};
