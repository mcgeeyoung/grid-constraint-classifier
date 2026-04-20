const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

export const DispatchChart = {
  props: {
    labels: { type: Array, required: true },
    datasets: { type: Array, required: true }, // [{label, data, kind:'line'|'bar'|'band', color}]
    height: { type: Number, default: 220 },
  },
  setup(props) {
    const canvas = ref(null);
    let chart = null;

    function draw() {
      if (!canvas.value) return;
      if (chart) chart.destroy();
      const ds = props.datasets.map((d) => {
        const base = { label: d.label, data: d.data, borderColor: d.color, backgroundColor: d.color };
        if (d.kind === "bar") return { ...base, type: "bar", borderWidth: 0 };
        if (d.kind === "band") return { ...base, type: "line", fill: "+1", backgroundColor: d.color + "33", pointRadius: 0, tension: 0.1 };
        return { ...base, type: "line", tension: 0.2, pointRadius: 0, spanGaps: true };
      });
      chart = new Chart(canvas.value.getContext("2d"), {
        data: { labels: props.labels, datasets: ds },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { labels: { color: "#F1FDFF" } } },
          scales: {
            x: { ticks: { color: "#6C8C93", maxRotation: 45 } },
            y: { ticks: { color: "#6C8C93" }, grid: { color: "rgba(11, 212, 255, 0.08)" } },
          },
        },
      });
    }
    onMounted(draw);
    watch(() => [props.labels, props.datasets], draw, { deep: true });
    onBeforeUnmount(() => chart && chart.destroy());
    return () => h("div", { class: "chart-wrap" },
      h("canvas", { ref: canvas, height: props.height }));
  },
};
