const { h } = Vue;

export const CommunitiesLeaderboard = {
  props: {
    // Zones from /api/v1/{utility_id}/admin/zones; each carries `label` and
    // `device_ids`. For tenants whose /zones endpoint still returns Dominion's
    // taxonomy (pre-existing scaffold limitation), the app also passes
    // zoneLabels from ui-config to override display names per-id.
    zones: { type: Array, required: true },
    zoneLabels: { type: Array, default: () => [] },
    participation30: { type: Object, required: true },
  },
  render() {
    const devices = this.participation30?.devices || [];
    const byZone = {};
    const deviceToZone = {};
    for (const z of this.zones) {
      for (const d of (z.device_ids || [])) deviceToZone[d] = z.id;
    }
    const labelOverride = {};
    for (const z of (this.zoneLabels || [])) {
      if (z && z.id) labelOverride[z.id] = z.label || z.id;
    }
    for (const d of devices) {
      const zid = deviceToZone[d.device_id_external];
      if (!zid) continue;
      byZone[zid] = byZone[zid] || { perfs: [], mwBase: 0 };
      if (d.participation_pct != null) byZone[zid].perfs.push(d.participation_pct);
      // MW = 700 kW × device count in the zone.
      byZone[zid].mwBase += 0.7;
    }
    const rows = this.zones.map((z) => {
      const agg = byZone[z.id] || { perfs: [], mwBase: 0 };
      const avgPerf = agg.perfs.length ? agg.perfs.reduce((a, b) => a + b, 0) / agg.perfs.length : null;
      return {
        id: z.id,
        // Prefer ui-config override label when present (handles tenants
        // whose /zones endpoint is still Dominion-scoped); else use the
        // label the backend returned; else the raw id.
        name: labelOverride[z.id] || z.label || z.id,
        mw: agg.mwBase,
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
