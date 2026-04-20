import { api } from "./api.js";
import { HeaderBar } from "./components/HeaderBar.js";
import { HeroMap } from "./components/HeroMap.js";
import { CommunityKwhCard } from "./components/CommunityKwhCard.js";
import { RatepayerValueCard } from "./components/RatepayerValueCard.js";
import { CommunitiesLeaderboard } from "./components/CommunitiesLeaderboard.js";
import { EventRibbon } from "./components/EventRibbon.js";
import { ScaleSlider } from "./components/ScaleSlider.js";

const { createApp, reactive, computed, h, onMounted } = Vue;

// Scale rule: "today" baseline is 5,000 devices against a 6-device DB pilot.
// scaleFactor is applied per-widget; the scaling-semantics table in the plan
// dictates which numbers multiply and which don't.
const BASE_DB_DEVICES = 6;

async function loadScenarios() {
  const res = await fetch("./refdata/scenarios.json");
  return res.json();
}

const App = {
  setup() {
    const state = reactive({
      loading: true,
      err: null,
      scenarios: [],       // [{id, label, deviceCount, peakMw, infra, citation}]
      scenario: null,      // currently selected scenario
      today: null,         // dashboardToday response
      zones: [],           // zones list
      events30: [],        // last 30 days event list
      participation30: null, // 30-day participation rollup
      participation7: null,  // 7-day participation rollup
      heatmap: null,       // latest congestion-heatmap response
    });

    const scaleFactor = computed(() =>
      state.scenario ? state.scenario.deviceCount / BASE_DB_DEVICES : 1
    );

    async function load() {
      try {
        const [scenarios, today, zones, events30, p30, p7, heat] = await Promise.all([
          loadScenarios(),
          api.dashboardToday(),
          api.zones(),
          api.events({ window_days: 30, limit: 200 }),
          api.participation({ window_days: 30 }),
          api.participation({ window_days: 7 }),
          api.congestionHeatmap(),
        ]);
        state.scenarios = scenarios;
        state.scenario = scenarios.find((s) => s.id === "today") || scenarios[0];
        state.today = today;
        state.zones = zones;
        state.events30 = events30.events || [];
        state.participation30 = p30;
        state.participation7 = p7;
        state.heatmap = heat;
        state.loading = false;
      } catch (e) {
        state.err = String(e.message || e);
        state.loading = false;
      }
    }

    function setScenario(id) {
      const next = state.scenarios.find((s) => s.id === id);
      if (next) state.scenario = next;
    }

    onMounted(load);

    return () => {
      if (state.loading) return h("div", { class: "loading" }, "Loading…");
      if (state.err) return h("div", { class: "panel error-text", style: { gridColumn: "1 / -1" } }, state.err);

      return [
        h(HeaderBar, {
          class: "exec-hdr panel",
          today: state.today,
        }),
        h(HeroMap, {
          class: "exec-map",
          heatmap: state.heatmap,
          zones: state.zones,
          events30: state.events30,
          scaleFactor: scaleFactor.value,
        }),
        h("div", { class: "exec-rail" }, [
          h(CommunityKwhCard,   { class: "panel kpi", participation7: state.participation7, scaleFactor: scaleFactor.value }),
          h(RatepayerValueCard, { class: "panel kpi", participation30: state.participation30, scaleFactor: scaleFactor.value }),
          h(CommunitiesLeaderboard, { class: "panel kpi", zones: state.zones, participation30: state.participation30, scaleFactor: scaleFactor.value }),
        ]),
        h(EventRibbon, {
          class: "exec-ribbon panel",
          events30: state.events30,
        }),
        h(ScaleSlider, {
          class: "exec-slider panel",
          scenarios: state.scenarios,
          current: state.scenario,
          onSelect: setScenario,
        }),
      ];
    };
  },
};

createApp(App).mount("#app");
