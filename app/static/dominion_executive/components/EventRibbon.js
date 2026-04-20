const { h, ref } = Vue;

function dayKey(isoLike) {
  // Use the operating_date from the event, not start_utc, to bucket correctly.
  return String(isoLike).slice(0, 10);
}

export const EventRibbon = {
  props: { events30: { type: Array, required: true } },
  setup(props) {
    // Aggregate events by operating_date. Red (mandatory) wins over
    // honeydew (optional-only) wins over sandy (no event).
    function bucket() {
      const buckets = new Map(); // dayKey -> "mand" | "opt" | null
      for (const ev of props.events30 || []) {
        const k = dayKey(ev.operating_date);
        const cur = buckets.get(k);
        if (ev.has_mandatory) buckets.set(k, "mand");
        else if (cur !== "mand") buckets.set(k, "opt");
      }
      return buckets;
    }
    return () => {
      const b = bucket();
      // Render last 30 calendar days ending at today UTC.
      const days = [];
      const today = new Date();
      for (let i = 29; i >= 0; i--) {
        const d = new Date(today);
        d.setUTCDate(today.getUTCDate() - i);
        const k = d.toISOString().slice(0, 10);
        days.push({ key: k, cls: b.get(k) || "" });
      }
      return h("div", null, [
        h("div", { class: "h" }, "30 days of grid stress · honeydew optional · red mandatory"),
        h("div", { class: "ribbon-strip" }, days.map((d) =>
          h("div", { class: ["cell", d.cls], title: d.key })
        )),
        h("div", { class: "disc" }, "Grid stress is a property of the grid itself; does not scale with device count."),
      ]);
    };
  },
};
