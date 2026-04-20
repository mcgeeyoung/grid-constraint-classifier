const { h, onMounted, onBeforeUnmount, ref } = Vue;

const STYLE_URL = "./refdata/maplibre-style.json";
const PILOT_URL = "./refdata/pilot_pnodes.json";

function congestionColorStops() {
  // Transparent at 0, honeydew at moderate, red at heavy.
  return [
    "interpolate", ["linear"], ["heatmap-density"],
    0, "rgba(0,0,0,0)",
    0.3, "rgba(228,253,127,0.35)",
    0.7, "rgba(228,253,127,0.8)",
    1, "rgba(229,83,75,0.9)",
  ];
}

async function loadJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`fetch ${url}: ${r.status}`);
  return r.json();
}

export const HeroMap = {
  props: {
    // Consumed once on map load; not re-watched.
    heatmap: { type: Object, required: true },
    zones: { type: Array, required: true },
    events30: { type: Array, required: true },
  },
  setup(props) {
    const el = ref(null);
    let map = null;
    const markers = [];

    async function init() {
      const style = await loadJson(STYLE_URL);
      map = new maplibregl.Map({
        container: el.value,
        style,
        center: [-77.6, 38.9],  // NoVA focus
        zoom: 7.6,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
      map.on("load", async () => {
        try {
          // Rolled-up congestion heat across the last 30 DA days.
          // Each point is a DOM LOAD pnode; weight = max abs congestion $/MWh seen in the window.
          const congestionFC = {
            type: "FeatureCollection",
            features: (props.heatmap?.points || []).map((p) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [p.lon, p.lat] },
              properties: { w: p.mean_abs_congestion },
            })),
          };
          map.addSource("congestion", { type: "geojson", data: congestionFC });
          map.addLayer({
            id: "congestion-heat",
            type: "heatmap",
            source: "congestion",
            maxzoom: 12,
            paint: {
              // Mean abs congestion across the 30-day window, typically 5-25 $/MWh.
              "heatmap-weight": ["interpolate", ["linear"], ["get", "w"], 0, 0, 10, 0.35, 20, 0.7, 30, 1],
              "heatmap-intensity": 1.1,
              "heatmap-color": congestionColorStops(),
              "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 18, 9, 45],
              "heatmap-opacity": 0.85,
            },
          });

          // Pilot pnode markers (the 6 enrolled devices). Labeled.
          const pilot = await loadJson(PILOT_URL);
          for (const p of (pilot.pnodes || [])) {
            const wrap = document.createElement("div");
            wrap.className = "pilot-marker-wrap";
            const dot = document.createElement("div");
            dot.className = "pilot-marker-dot";
            const label = document.createElement("div");
            label.className = "pilot-marker-label";
            label.textContent = p.pnode_name;
            wrap.appendChild(dot);
            wrap.appendChild(label);
            const m = new maplibregl.Marker({ element: wrap, anchor: "center" })
              .setLngLat([p.lon, p.lat])
              .addTo(map);
            markers.push(m);
          }
        } catch (e) {
          console.error("HeroMap: layer init failed", e);
        }
      });
    }

    onMounted(init);
    onBeforeUnmount(() => {
      for (const m of markers) m.remove();
      markers.length = 0;
      if (map) { map.remove(); map = null; }
    });

    return () => h("div", {
      ref: el,
      style: { width: "100%", height: "100%", minHeight: "28rem" },
    });
  },
};
