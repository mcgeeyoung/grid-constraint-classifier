const { h, onMounted, onBeforeUnmount, ref } = Vue;

// Shared WattCarbon basemap style. Per-tenant pilot pnodes + map center now
// arrive via props from /ui-config; no per-utility static files.
const STYLE_URL = "./refdata/maplibre-style.json";

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
    // Tenant pilot pnodes from /ui-config (replaces ./refdata/pilot_pnodes.json).
    pilotPnodes: { type: Array, default: () => [] },
    // [lat, lon] from ui-config. Defaults keep the Dominion view if absent.
    center: { type: Array, default: () => [38.9, -77.6] },
    zoom: { type: Number, default: 7.6 },
  },
  setup(props) {
    const el = ref(null);
    let map = null;
    const markers = [];

    async function init() {
      const style = await loadJson(STYLE_URL);
      // ui-config stores [lat, lon]; MapLibre wants [lon, lat].
      const cLatLon = (props.center && props.center.length >= 2)
        ? [Number(props.center[0]), Number(props.center[1])]
        : [38.9, -77.6];
      map = new maplibregl.Map({
        container: el.value,
        style,
        center: [cLatLon[1], cLatLon[0]],
        zoom: Number(props.zoom) || 7.6,
        attributionControl: true,
      });
      map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
      map.on("load", () => {
        try {
          // Rolled-up congestion heat across the last 30 DA days.
          // Each point is a LOAD pnode; weight = mean abs congestion $/MWh in the window.
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

          // Pilot pnode markers. Labeled.
          for (const p of (props.pilotPnodes || [])) {
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
