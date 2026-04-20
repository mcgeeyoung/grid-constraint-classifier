const { h } = Vue;

function fmt(n) { return Number(n).toLocaleString(); }

export const EnrollmentProgress = {
  props: {
    milestones: { type: Array, required: true },
    // Short geo phrase, e.g. "Northern Virginia" or "Northern California".
    subLocation: { type: String, default: "" },
  },
  render() {
    const ms = (this.milestones || []).slice();
    if (ms.length === 0) return h("div", null, "No milestones configured.");

    // Today's enrollment is the first stop in the list (id "today").
    // Goal is the last stop (largest deviceCount).
    const today = ms[0];
    const goal = ms[ms.length - 1];
    const midMilestones = ms.slice(1, -1);

    const todayPct = (today.deviceCount / goal.deviceCount) * 100;
    const remaining = goal.deviceCount - today.deviceCount;
    const nextMs = midMilestones.length > 0 ? midMilestones[0] : goal;
    const toNext = Math.max(0, nextMs.deviceCount - today.deviceCount);

    // Derive a region word for the headline ("Virginia", "California", ...)
    // from subLocation. Falls back to the tenant-neutral "enrolled" if not
    // recognized.
    const stateMatch = String(this.subLocation || "").match(
      /(Virginia|California|Maryland|New York|Pennsylvania|Illinois|Texas|Ohio|Michigan|New Jersey)\b/
    );
    const regionWord = stateMatch ? stateMatch[1] : "enrolled";

    return h("div", null, [
      h("div", { class: "h" }, `Enrollment progress · toward ${fmt(goal.deviceCount)} ${regionWord} devices`),

      h("div", { class: "enrollment-headline" }, [
        h("span", { class: "enrollment-count" }, `${fmt(today.deviceCount)} enrolled`),
        h("span", { class: "enrollment-pct" }, `${todayPct.toFixed(1)}% of goal`),
        h("span", { class: "enrollment-gap" }, `${fmt(remaining)} to go`),
      ]),

      h("div", { class: "enrollment-track" }, [
        h("div", { class: "enrollment-fill", style: { width: `${todayPct}%` } }),
        h("div", { class: "enrollment-today-marker", style: { left: `${todayPct}%` } },
          h("div", { class: "enrollment-today-label" }, "today")),
        ...midMilestones.map((m) => {
          const pct = (m.deviceCount / goal.deviceCount) * 100;
          return h("div", { class: "enrollment-milestone", style: { left: `${pct}%` } }, [
            h("div", { class: "enrollment-milestone-tick" }),
            h("div", { class: "enrollment-milestone-label" }, [
              h("div", { class: "enrollment-milestone-count" }, `${fmt(m.deviceCount)}`),
              h("div", { class: "enrollment-milestone-infra" }, m.infra),
            ]),
          ]);
        }),
        h("div", { class: "enrollment-goal", style: { left: "100%" } }, [
          h("div", { class: "enrollment-milestone-tick" }),
          h("div", { class: "enrollment-goal-label" }, [
            h("div", { class: "enrollment-milestone-count" }, `${fmt(goal.deviceCount)}`),
            h("div", { class: "enrollment-milestone-infra" }, goal.infra),
          ]),
        ]),
      ]),

      h("div", { class: "disc" },
        midMilestones.length > 0
          ? `Next milestone at ${fmt(nextMs.deviceCount)} devices (${fmt(toNext)} more enrollments). ${nextMs.infra}`
          : `Goal: ${goal.infra}`),
    ]);
  },
};
