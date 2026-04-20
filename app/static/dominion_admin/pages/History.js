import { EventRow } from "../components/EventRow.js";

const { h, ref, onMounted, watch } = Vue;

const WINDOWS = [
  { label: "30d", value: 30 },
  { label: "90d", value: 90 },
  { label: "365d", value: 365 },
];

export const History = {
  components: { EventRow },
  props: { api: { type: Object, required: true } },
  setup(props) {
    const state = ref({ loading: true, err: null });
    const zones = ref([]);
    const rows = ref([]);
    const windowDays = ref(30);
    const zoneId = ref(null);
    const hasMand = ref(null);
    const minPerf = ref(null);

    async function load() {
      state.value = { loading: true, err: null };
      try {
        if (!zones.value.length) zones.value = await props.api.zones();
        const params = { window_days: windowDays.value, limit: 200 };
        if (zoneId.value) params.zone_id = zoneId.value;
        if (hasMand.value != null) params.has_mandatory = hasMand.value;
        if (minPerf.value != null) params.min_perf = minPerf.value;
        const r = await props.api.events(params);
        rows.value = r.events;
        state.value = { loading: false, err: null };
      } catch (e) {
        state.value = { loading: false, err: String(e.message || e) };
      }
    }
    onMounted(load);
    watch([windowDays, zoneId, hasMand, minPerf], load);

    return () => {
      return h("div", null, [
        h("div", { class: "crumb" }, [h("a", { href: "#/" }, "Dashboard"), " › ", h("span", null, "History")]),
        h("div", { class: "panel" }, [
          h("div", { class: "filters" }, [
            ...WINDOWS.map((w) => h("span", {
              class: `filter ${windowDays.value === w.value ? "active" : ""}`,
              onClick: () => (windowDays.value = w.value),
            }, w.label)),
            h("span", { class: "filter muted" }, "zone:"),
            h("span", {
              class: `filter ${zoneId.value == null ? "active" : ""}`,
              onClick: () => (zoneId.value = null),
            }, "all"),
            ...zones.value.map((z) => h("span", {
              class: `filter ${zoneId.value === z.id ? "active" : ""}`,
              onClick: () => (zoneId.value = z.id),
            }, z.label)),
            h("span", {
              class: `filter ${hasMand.value === true ? "active" : ""}`,
              onClick: () => (hasMand.value = hasMand.value === true ? null : true),
            }, "mandatory-only"),
            h("span", {
              class: `filter ${minPerf.value === 85 ? "active" : ""}`,
              onClick: () => (minPerf.value = minPerf.value === 85 ? null : 85),
            }, "perf ≥ 85%"),
          ]),
          state.value.loading ? h("div", { class: "loading" }, "Loading…") :
          state.value.err ? h("div", { class: "error-text" }, state.value.err) :
          h("table", null, [
            h("thead", null, h("tr", null, ["Event", "Start", "Zone", "Pnode", "Tier", "Listed avg", "Realized avg", "Perf"].map((t) => h("th", null, t)))),
            h("tbody", null, rows.value.map((ev) => h(EventRow, { ev }))),
          ]),
        ]),
      ]);
    };
  },
};
