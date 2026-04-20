const { h } = Vue;

export const HeaderBar = {
  props: { today: { type: Object, required: true } },
  render() {
    const t = this.today;
    const basisLabel = t.forecast_basis === "tomorrow_da" ? "PJM DA tomorrow" : "latest cleared DA";
    const peakMw = (t.peak_program_kw / 1000).toFixed(1);
    return h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%" } }, [
      h("div", { class: "lead" },
        `Virginia communities deliver back to Dominion's grid.`),
      h("div", { class: "grid-state" }, [
        h("div", { class: "h" }, `${basisLabel} · ${t.operating_date}`),
        h("div", { class: "v" }, `${t.events_forecast} events · ${peakMw} MW peak`),
      ]),
    ]);
  },
};
