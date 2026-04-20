const { h } = Vue;

export const ScaleSlider = {
  props: {
    scenarios: { type: Array, required: true },
    current: { type: Object, required: true },
    onSelect: { type: Function, required: true },
  },
  render() {
    return h("div", null, [
      h("div", { class: "h" }, "Scale scenarios"),
      h("div", { class: "slider-stops" }, this.scenarios.map((s) =>
        h("div", {
          class: ["slider-stop", this.current && this.current.id === s.id ? "active" : ""],
          onClick: () => this.onSelect(s.id),
        }, [
          h("div", { class: "num" }, `${s.deviceCount.toLocaleString()} devices`),
          h("div", { class: "mw" }, `${s.peakMw.toLocaleString()} MW peak`),
          h("div", { class: "infra" }, s.infra),
        ])
      )),
      h("div", { class: "disc" }, "Linear scaling. Real-world saturation at 230 kV substations not modeled."),
    ]);
  },
};
