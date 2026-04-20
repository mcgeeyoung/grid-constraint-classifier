const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

const STYLE_URL = "./refdata/maplibre-style.json";
const SYNTH_URL = "./refdata/synth_devices_va.json";

function heatmapColorStops() {
  // Transparent at weight 0, honeydew (#E4FD7F), red (#E5534B) at heavy.
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
    heatmap: { type: Object, required: true },
    zones: { type: Array, required: true },
    events30: { type: Array, required: true },
    scaleFactor: { type: Number, required: true },
  },
  setup(props) {
    const el = ref(null);
    let map = null;
    let synthPoints = [];

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
            "heatmap-color": heatmapColorStops(),
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 18, 9, 45],
            "heatmap-opacity": 0.85,
          },
        });

        // Synthesized device density layer.
        const synth = await loadJson(SYNTH_URL);
        synthPoints = synth.points || [];
        map.addSource("devices", {
          type: "geojson",
          data: synthFeatureCollection(synthPoints, props.scaleFactor),
        });
        map.addLayer({
          id: "devices-heat",
          type: "heatmap",
          source: "devices",
          paint: {
            "heatmap-weight": 0.05,
            "heatmap-intensity": ["interpolate", ["linear"], ["get", "intensity"], 0, 0.2, 1, 1.0],
            "heatmap-color": [
              "interpolate", ["linear"], ["heatmap-density"],
              0, "rgba(0,0,0,0)",
              0.3, "rgba(11,212,255,0.2)",
              0.7, "rgba(11,212,255,0.5)",
              1, "rgba(228,253,127,0.7)",
            ],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 12, 9, 30],
            "heatmap-opacity": 0.75,
          },
        });
      });
    }

    function synthFeatureCollection(points, scaleFactor) {
      // At scaleFactor=1 (today), render the 5,000 points once; heatmap is
      // governed by heatmap-weight. At scaleFactor > 1, duplicate with jitter
      // and ramp the weight up via the "intensity" property.
      // Rather than multiplying the JSON array by 10x/100x (performance hit),
      // multiply a per-point "intensity" property and rely on heatmap-weight.
      const reps = scaleFactor <= 1 ? 1 : scaleFactor <= 20 ? 2 : 4;
      const features = [];
      const rand = mulberry32(20260419);
      for (let r = 0; r < reps; r++) {
        for (const p of points) {
          const jitter = r === 0 ? 0 : 0.01;
          features.push({
            type: "Feature",
            geometry: {
              type: "Point",
              coordinates: [
                p.lon + (rand() - 0.5) * 2 * jitter,
                p.lat + (rand() - 0.5) * 2 * jitter,
              ],
            },
            properties: { intensity: Math.min(1, scaleFactor / 100) },
          });
        }
      }
      return { type: "FeatureCollection", features };
    }

    // Tiny deterministic PRNG
    function mulberry32(seed) {
      let a = seed;
      return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
    }

    watch(() => props.scaleFactor, (sf) => {
      if (!map || !map.getSource("devices")) return;
      map.getSource("devices").setData(synthFeatureCollection(synthPoints, sf));
    });

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
