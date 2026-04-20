const { h } = Vue;

// Zone → human label (UX-friendly names, not zone IDs).
const ZONE_DISPLAY = {
  "loudoun-corridor": "Loudoun",
  "fairfax-230":      "Fairfax",
  "alexandria":       "Alexandria",
};

export const CommunitiesLeaderboard = {
  props: {
    zones: { type: Array, required: true },
    participation30: { type: Object, required: true },
    scaleFactor: { type: Number, required: true },
  },
  render() {
    const devices = this.participation30?.devices || [];
    // Group perf by zone from device rows, then order by average perf.
    const byZone = {};
    // Build zone-membership lookup from this.zones.
    const deviceToZone = {};
    for (const z of this.zones) {
      for (const d of (z.device_ids || [])) deviceToZone[d] = z.id;
    }
    for (const d of devices) {
      const zid = deviceToZone[d.device_id_external];
      if (!zid) continue;
      byZone[zid] = byZone[zid] || { perfs: [], mwBase: 0 };
      if (d.participation_pct != null) byZone[zid].perfs.push(d.participation_pct);
      // Rough MW = listed capacity fraction × scale. Use 700 kW × device count.
      byZone[zid].mwBase += 0.7;
    }
    const rows = this.zones.map((z) => {
      const agg = byZone[z.id] || { perfs: [], mwBase: 0 };
      const avgPerf = agg.perfs.length ? agg.perfs.reduce((a, b) => a + b, 0) / agg.perfs.length : null;
      const scaledMw = agg.mwBase * this.scaleFactor;
      return {
        id: z.id,
        name: ZONE_DISPLAY[z.id] || z.label,
        mw: scaledMw,
        perf: avgPerf,
      };
    }).sort((a, b) => (b.perf || 0) - (a.perf || 0));

    return h("div", null, [
      h("div", { class: "h" }, "Communities leaderboard"),
      ...rows.map((r) => h("div", { class: "leaderboard-row" }, [
        h("span", { class: "name" }, r.name),
        h("span", { class: "meta" }, `${r.mw.toFixed(1)} MW · ${r.perf != null ? r.perf.toFixed(0) + "%" : "-"}`),
      ])),
    ]);
  },
};
