const { h, onMounted, onBeforeUnmount, ref, watch } = Vue;

export const ZoneMap = {
  props: {
    devices: { type: Array, required: true },   // [{device_id, zone_id, asset_lat, asset_lon, listed_capacity_kw, perf_pct}]
    pnodeCoords: { type: Object, default: () => ({}) }, // primary_pnode_id -> [lat, lon]
    minHeight: { type: String, default: "20rem" },
    id: { type: String, default: "map-leaflet" },
  },
  setup(props) {
    const mapEl = ref(null);
    let map = null;
    let markers = [];

    function colorForPerf(pct) {
      if (pct == null) return "#6C8C93";       // wc-sandy
      if (pct >= 90) return "#E4FD7F";         // wc-honeydew
      if (pct >= 75) return "#0BD4FF";         // wc-neon
      return "#6C8C93";                        // wc-sandy (demote, no red in brand)
    }

    function renderMarkers() {
      if (!map) return;
      markers.forEach((m) => m.remove());
      markers = [];
      const pts = [];
      for (const d of props.devices) {
        const color = colorForPerf(d.perf_pct);
        if (d.asset_lat != null && d.asset_lon != null) {
          const m = L.circleMarker([d.asset_lat, d.asset_lon], {
            radius: 8, color, fillColor: "#E4FD7F", fillOpacity: 0.6, weight: 2,
          }).bindPopup(`<b>${d.device_id_external}</b><br>listed ${d.listed_capacity_kw || "-"} kW<br>perf ${d.perf_pct != null ? d.perf_pct.toFixed(0) + "%" : "-"}`)
            .addTo(map);
          markers.push(m);
          pts.push([d.asset_lat, d.asset_lon]);
        }
        const coords = props.pnodeCoords[d.primary_pnode_id];
        if (coords) {
          const m = L.circleMarker(coords, {
            radius: 6, color: "#0697B6", fillColor: "#C0F5FF", fillOpacity: 0.6, weight: 2,
          }).bindPopup(`<b>pnode ${d.primary_pnode_id}</b>`).addTo(map);
          markers.push(m);
          pts.push(coords);
        }
      }
      if (pts.length) map.fitBounds(pts, { padding: [20, 20] });
    }

    onMounted(() => {
      map = L.map(mapEl.value, { zoomControl: true }).setView([38.9, -77.35], 9);
      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        attribution: "© OSM © CARTO", subdomains: "abcd", maxZoom: 19,
      }).addTo(map);
      renderMarkers();
    });
    watch(() => [props.devices, props.pnodeCoords], renderMarkers, { deep: true });
    onBeforeUnmount(() => map && map.remove());

    return () => h("div", {
      id: props.id,
      ref: mapEl,
      style: { minHeight: props.minHeight, width: "100%" },
    });
  },
};
