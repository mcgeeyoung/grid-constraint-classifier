const { h, onMounted, onBeforeUnmount, ref } = Vue;

const STYLE_URL = "./refdata/maplibre-style.json";
const SYNTH_URL = "./refdata/synth_devices_va.json";

function congestionColorStops() {
  // Transparent at weight 0, honeydew (#E4FD7F), red (#E5534B) at heavy.
  return [
    "interpolate", ["linear"], ["heatmap-density"],
    0, "rgba(0,0,0,0)",
    0.3, "rgba(228,253,127,0.35)",
    0.7, "rgba(228,253,127,0.8)",
    1, "rgba(229,83,75,0.9)",
  ];
}

function devicesColorStops() {
  return [
    "interpolate", ["linear"], ["heatmap-density"],
    0, "rgba(0,0,0,0)",
    0.3, "rgba(11,212,255,0.2)",
    0.7, "rgba(11,212,255,0.5)",
    1, "rgba(228,253,127,0.7)",
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

    async function init() {
      const style = await loadJson(STYLE_URL);
      map = new maplibregl.Map({
        container: el.value,
        style,
        center: [-78.6, 37.8],  // VA approx
        zoom: 6.4,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
      map.on("load", async () => {
        try {
          // Real congestion heatmap from the heatmap API.
          const congestionFC = {
            type: "FeatureCollection",
            features: (props.heatmap?.points || []).map((p) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [p.lon, p.lat] },
              properties: { w: p.max_abs_congestion },
            })),
          };
          map.addSource("congestion", { type: "geojson", data: congestionFC });
          map.addLayer({
            id: "congestion-heat",
            type: "heatmap",
            source: "congestion",
            maxzoom: 12,
            paint: {
              "heatmap-weight": ["interpolate", ["linear"], ["get", "w"], 0, 0, 40, 0.6, 100, 1],
              "heatmap-intensity": 1.1,
              "heatmap-color": congestionColorStops(),
              "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 18, 9, 45],
              "heatmap-opacity": 0.85,
            },
          });

          // Static residential-density backdrop: 5,000 deterministic synthetic
          // residential points across Dominion Virginia Power service territory.
          // Shows where devices would enroll if the program scaled; does not
          // represent actual enrolled devices.
          const synth = await loadJson(SYNTH_URL);
          const synthFC = {
            type: "FeatureCollection",
            features: (synth.points || []).map((p) => ({
              type: "Feature",
              geometry: { type: "Point", coordinates: [p.lon, p.lat] },
            })),
          };
          map.addSource("devices", { type: "geojson", data: synthFC });
          map.addLayer({
            id: "devices-heat",
            type: "heatmap",
            source: "devices",
            paint: {
              "heatmap-weight": 0.05,
              "heatmap-intensity": 0.7,
              "heatmap-color": devicesColorStops(),
              "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 12, 9, 30],
              "heatmap-opacity": 0.65,
            },
          });
        } catch (e) {
          console.error("HeroMap: layer init failed", e);
        }
      });
    }

    onMounted(init);
    onBeforeUnmount(() => {
      if (map) { map.remove(); map = null; }
    });

    return () => h("div", {
      ref: el,
      style: { width: "100%", height: "100%", minHeight: "28rem" },
    });
  },
};
