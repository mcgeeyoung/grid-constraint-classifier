import { api, UTILITY_ID } from "./api.js";
import { HeaderBar } from "./components/HeaderBar.js";
import { HeroMap } from "./components/HeroMap.js";
import { CommunityKwhCard } from "./components/CommunityKwhCard.js";
import { RatepayerValueCard } from "./components/RatepayerValueCard.js";
import { CommunitiesLeaderboard } from "./components/CommunitiesLeaderboard.js";
import { EventRibbon } from "./components/EventRibbon.js";
import { EnrollmentProgress } from "./components/EnrollmentProgress.js";

const { createApp, reactive, h, onMounted } = Vue;

const App = {
  setup() {
    const state = reactive({
      loading: true,
      err: null,
      uiConfig: null,        // tenant copy + zones + scenarios + pilot_pnodes
      today: null,           // dashboardToday response
      zones: [],             // zones list (mirrors uiConfig.zones; from /zones)
      events30: [],          // last 30 days event list
      participation30: null, // 30-day participation rollup
      participation7: null,  // 7-day participation rollup
      heatmap: null,         // latest congestion-heatmap response
    });

    async function load() {
      try {
        const [uiConfig, today, zones, events30, p30, p7, heat] = await Promise.all([
          api.uiConfig(),
          api.dashboardToday(),
          api.zones(),
          api.events({ window_days: 30, limit: 200 }),
          api.participation({ window_days: 30 }),
          api.participation({ window_days: 7 }),
          api.congestionHeatmap({ window_days: 30 }),
        ]);
        state.uiConfig = uiConfig;
        state.today = today;
        state.zones = zones;
        state.events30 = events30.events || [];
        state.participation30 = p30;
        state.participation7 = p7;
        state.heatmap = heat;
        // Retitle the tab and the header chip to the tenant's program name.
        if (uiConfig && uiConfig.program_name) {
          document.title = `${uiConfig.program_name} · WattCarbon`;
          const ctx = document.querySelector(".wc-brand-header .wc-context");
          if (ctx) ctx.textContent = uiConfig.program_name;
        }
        // Dominion ships two sibling consoles (admin + demo). Other tenants
        // don't have them yet, so only render the footer links for Dominion.
        const footerLinks = document.querySelector("[data-footer-links]");
        if (footerLinks && UTILITY_ID === "dominion") {
          while (footerLinks.firstChild) footerLinks.removeChild(footerLinks.firstChild);
          const a1 = document.createElement("a");
          a1.href = "/dominion-admin/";
          a1.textContent = "Operations console";
          const sep = document.createTextNode(" · ");
          const a2 = document.createElement("a");
          a2.href = "/dominion-demo/";
          a2.textContent = "Engineering walkthrough";
          footerLinks.appendChild(a1);
          footerLinks.appendChild(sep);
          footerLinks.appendChild(a2);
        }
        state.loading = false;
      } catch (e) {
        state.err = String(e.message || e);
        state.loading = false;
      }
    }

    onMounted(load);

    return () => {
      if (state.loading) return h("div", { class: "loading" }, "Loading…");
      if (state.err) return h("div", { class: "panel error-text", style: { gridColumn: "1 / -1" } }, state.err);

      const cfg = state.uiConfig || {};
      return [
        h(HeaderBar, {
          class: "exec-hdr panel",
          today: state.today,
          headlineLead: cfg.headline_lead,
        }),
        h(HeroMap, {
          class: "exec-map",
          heatmap: state.heatmap,
          zones: state.zones,
          events30: state.events30,
          pilotPnodes: cfg.pilot_pnodes || [],
          center: cfg.service_territory_center,
          zoom: cfg.service_territory_zoom,
        }),
        h("div", { class: "exec-rail" }, [
          h(CommunityKwhCard, {
            class: "panel kpi",
            participation7: state.participation7,
            pilotPnodes: cfg.pilot_pnodes || [],
            subLocation: cfg.community_sub_location,
          }),
          h(RatepayerValueCard, {
            class: "panel kpi",
            participation30: state.participation30,
            settlementRateUsdPerMwh: cfg.settlement_rate_usd_per_mwh,
            settlementRateDescription: cfg.settlement_rate_description,
            subLocation: cfg.community_sub_location,
          }),
          h(CommunitiesLeaderboard, {
            class: "panel kpi",
            // Prefer zones from /zones (carries device_ids for Dominion);
            // fall back to ui-config zones on tenants without device rows.
            zones: (state.zones && state.zones.length) ? state.zones : (cfg.zones || []),
            // Pass ui-config zones as an override so tenants whose /zones
            // endpoint still returns Dominion's taxonomy (pre-existing scaffold
            // limitation) can still display the correct labels.
            zoneLabels: cfg.zones || [],
            participation30: state.participation30,
          }),
        ]),
        h(EventRibbon, {
          class: "exec-ribbon panel",
          events30: state.events30,
        }),
        h(EnrollmentProgress, {
          class: "exec-slider panel",
          milestones: cfg.scenarios || [],
          subLocation: cfg.community_sub_location,
        }),
      ];
    };
  },
};

createApp(App).mount("#app");

// Expose for debug; harmless in prod.
if (typeof window !== "undefined") window.__UTILITY_ID_RUNTIME__ = UTILITY_ID;
