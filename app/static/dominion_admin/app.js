import { api } from "./api.js";
import { Dashboard } from "./pages/Dashboard.js";
import { EventDetail } from "./pages/EventDetail.js";
import { DeviceDetail } from "./pages/DeviceDetail.js";
import { History } from "./pages/History.js";

const { createApp, reactive, ref, computed, h, onMounted, watch } = Vue;

const ROUTES = [
  { re: /^\/?$/,                     name: "dashboard",    component: Dashboard,   params: () => ({}) },
  { re: /^\/events\/([^/]+)\/?$/,    name: "event-detail", component: EventDetail, params: (m) => ({ eventId: decodeURIComponent(m[1]) }) },
  { re: /^\/devices\/([^/]+)\/?$/,   name: "device-detail",component: DeviceDetail,params: (m) => ({ deviceId: decodeURIComponent(m[1]) }) },
  { re: /^\/history\/?$/,            name: "history",      component: History,     params: () => ({}) },
];

function match(hash) {
  const path = (hash || "#/").replace(/^#/, "") || "/";
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (m) return { route: r, params: r.params(m) };
  }
  return { route: ROUTES[0], params: {} };
}

const App = {
  setup() {
    const current = ref(match(window.location.hash));
    const onHash = () => { current.value = match(window.location.hash); };
    window.addEventListener("hashchange", onHash);
    watch(current, () => {
      document.querySelectorAll("nav a").forEach((a) => {
        a.classList.toggle("active", a.dataset.route === (window.location.hash.replace(/^#/, "") || "/"));
      });
    }, { immediate: true });

    return () => h(current.value.route.component, { api, ...current.value.params });
  },
};

createApp(App).mount("#app");
