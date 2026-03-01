"""
GRIP distribution overlay: combined TX+DX risk scoring per PG&E division.

Joins PNode congestion scores to GRIP substation loading data via the
match table (name + proximity matches). Produces division-level risk
assessment and substation-level hotspot rankings.
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_series(s: pd.Series) -> pd.Series:
    """Min-max normalize a Series to [0, 1]."""
    smin, smax = s.min(), s.max()
    if smax - smin < 1e-9:
        return pd.Series(0.5, index=s.index)
    return (s - smin) / (smax - smin)


def _risk_label(tx_risk: float, dx_risk: float) -> str:
    """Assign risk label based on TX and DX risk scores."""
    if tx_risk >= 0.5 and dx_risk >= 0.5:
        return "CRITICAL"
    elif tx_risk >= 0.5 or dx_risk >= 0.5:
        return "ELEVATED"
    elif tx_risk >= 0.25 or dx_risk >= 0.25:
        return "MODERATE"
    return "LOW"


def compute_division_overlay(
    pnode_scores_df: pd.DataFrame,
    grip_df: pd.DataFrame,
    match_df: pd.DataFrame,
) -> list[dict]:
    """
    Compute combined TX+DX risk scores per PG&E division.

    Args:
        pnode_scores_df: DataFrame with pnode_name, avg_congestion, max_congestion,
                         severity_score, tier columns (from pnode_analyzer all_scored)
        grip_df: GRIP substation DataFrame with division, peakfacilityloadingpercent, etc.
        match_df: PNode-GRIP match table from grip_matcher

    Returns:
        List of division dicts with risk scores, sorted by combined_risk desc.
    """
    if match_df.empty:
        logger.warning("No PNode-GRIP matches, cannot compute division overlay")
        return []

    # Build PNode congestion lookup: prefix -> avg congestion across all PNodes with that prefix
    pnode_prefix_cong = {}
    for _, row in pnode_scores_df.iterrows():
        pname = str(row.get("pnode_name", ""))
        prefix = pname.split("_")[0].upper().strip() if pname else ""
        if prefix:
            pnode_prefix_cong.setdefault(prefix, []).append({
                "avg_congestion": row.get("avg_congestion", 0),
                "max_congestion": row.get("max_congestion", 0),
                "severity_score": row.get("severity_score", 0),
                "tier": row.get("tier", "low"),
            })

    # Join match info to get per-division congestion stats
    division_data = {}
    for _, m in match_df.iterrows():
        prefix = m.get("caiso_prefix", "")
        division = m.get("division", "")
        if not division:
            continue

        cong_entries = pnode_prefix_cong.get(prefix, [])
        if not cong_entries:
            continue

        div = division_data.setdefault(division, {
            "congestion_values": [],
            "max_congestion_values": [],
            "severity_scores": [],
            "tiers": [],
        })
        for c in cong_entries:
            div["congestion_values"].append(c["avg_congestion"])
            div["max_congestion_values"].append(c["max_congestion"])
            div["severity_scores"].append(c["severity_score"])
            div["tiers"].append(c["tier"])

    # Compute GRIP distribution stats per division
    grip_div_stats = {}
    for division, ddf in grip_df.groupby("division"):
        loading = pd.to_numeric(ddf["peakfacilityloadingpercent"], errors="coerce")
        grip_div_stats[division] = {
            "n_banks": len(ddf),
            "avg_loading": round(loading.mean(), 2) if not loading.empty else 0,
            "banks_over_80": int((loading >= 80).sum()),
            "banks_over_100": int((loading >= 100).sum()),
        }

    # Build division overlay rows
    rows = []
    all_divisions = set(list(division_data.keys()) + list(grip_div_stats.keys()))

    for division in sorted(all_divisions):
        cong = division_data.get(division, {})
        grip = grip_div_stats.get(division, {
            "n_banks": 0, "avg_loading": 0, "banks_over_80": 0, "banks_over_100": 0
        })

        cong_vals = cong.get("congestion_values", [])
        avg_cong = sum(cong_vals) / len(cong_vals) if cong_vals else 0
        max_cong_vals = cong.get("max_congestion_values", [])
        max_cong = max(max_cong_vals) if max_cong_vals else 0
        severity_vals = cong.get("severity_scores", [])
        avg_score = sum(severity_vals) / len(severity_vals) if severity_vals else 0
        tiers = cong.get("tiers", [])
        pct_critical = tiers.count("critical") / len(tiers) if tiers else 0
        pct_elevated = tiers.count("elevated") / len(tiers) if tiers else 0

        rows.append({
            "division": division,
            "n_pnodes": len(cong_vals),
            "avg_congestion": round(avg_cong, 2),
            "max_congestion": round(max_cong, 2),
            "pct_critical": round(pct_critical, 4),
            "pct_elevated": round(pct_elevated, 4),
            "avg_score": round(avg_score, 4),
            "n_banks": grip["n_banks"],
            "avg_loading": grip["avg_loading"],
            "banks_over_80": grip["banks_over_80"],
            "banks_over_100": grip["banks_over_100"],
        })

    if not rows:
        return []

    df = pd.DataFrame(rows)

    # Normalize TX and DX risk to [0, 1]
    df["tx_risk"] = _normalize_series(df["avg_congestion"])
    df["dx_risk"] = _normalize_series(df["avg_loading"])
    df["combined_risk"] = (0.5 * df["tx_risk"] + 0.5 * df["dx_risk"]).round(4)
    df["risk"] = df.apply(lambda r: _risk_label(r["tx_risk"], r["dx_risk"]), axis=1)
    df["tx_risk"] = df["tx_risk"].round(4)
    df["dx_risk"] = df["dx_risk"].round(4)

    result = df.sort_values("combined_risk", ascending=False).to_dict("records")

    risk_counts = df["risk"].value_counts().to_dict()
    logger.info(
        f"Division overlay: {len(result)} divisions | "
        f"CRITICAL={risk_counts.get('CRITICAL', 0)} "
        f"ELEVATED={risk_counts.get('ELEVATED', 0)} "
        f"MODERATE={risk_counts.get('MODERATE', 0)} "
        f"LOW={risk_counts.get('LOW', 0)}"
    )

    return result


def build_substation_hotspots(
    pnode_scores_df: pd.DataFrame,
    grip_df: pd.DataFrame,
    match_df: pd.DataFrame,
    top_n: int = 25,
) -> list[dict]:
    """
    Build a ranked list of individual substation hotspots.

    For each GRIP substation, looks up its matched PNode congestion
    and computes a combined risk score.

    Args:
        pnode_scores_df: PNode scores from pnode_analyzer
        grip_df: GRIP substation DataFrame
        match_df: PNode-GRIP match table
        top_n: Number of top hotspots to return

    Returns:
        List of substation dicts sorted by combined risk score.
    """
    if match_df.empty:
        return []

    # Build PNode congestion lookup by prefix
    pnode_prefix_cong = {}
    for _, row in pnode_scores_df.iterrows():
        pname = str(row.get("pnode_name", ""))
        prefix = pname.split("_")[0].upper().strip() if pname else ""
        if prefix not in pnode_prefix_cong:
            pnode_prefix_cong[prefix] = {
                "avg_congestion": row.get("avg_congestion", 0),
                "max_congestion": row.get("max_congestion", 0),
                "severity_score": row.get("severity_score", 0),
            }

    # Build GRIP substation lookup (use first bank per substation for loading)
    grip_sub_info = {}
    for _, row in grip_df.iterrows():
        sub = row.get("sub_clean", "")
        if sub and sub not in grip_sub_info:
            loading = pd.to_numeric(row.get("peakfacilityloadingpercent", 0), errors="coerce")
            rating = pd.to_numeric(row.get("facilityratingmw", 0), errors="coerce")
            grip_sub_info[sub] = {
                "loading_pct": loading if not pd.isna(loading) else 0,
                "rating_mw": rating if not pd.isna(rating) else 0,
                "division": row.get("division", ""),
            }

    hotspots = []
    for _, m in match_df.iterrows():
        prefix = m.get("caiso_prefix", "")
        grip_sub = m.get("grip_substation", "")
        match_type = m.get("match_type", "name")
        distance_km = m.get("distance_km", 0)

        cong = pnode_prefix_cong.get(prefix, {})
        sub_info = grip_sub_info.get(grip_sub, {})

        avg_congestion = cong.get("avg_congestion", 0)
        loading_pct = sub_info.get("loading_pct", 0)

        # Combined risk: congestion severity * loading fraction
        risk = avg_congestion * (loading_pct / 100.0) if loading_pct > 0 else 0

        # Determine nearest PNode name for display
        pnode_display = m.get("pnode_names", prefix)
        if ";" in str(pnode_display):
            pnode_display = str(pnode_display).split(";")[0]

        hotspots.append({
            "substation": grip_sub,
            "division": m.get("division", sub_info.get("division", "")),
            "nearest_pnode": pnode_display,
            "match_type": match_type,
            "distance_km": round(float(distance_km), 1),
            "avg_congestion": round(avg_congestion, 2),
            "loading_pct": round(loading_pct, 1),
            "rating_mw": round(sub_info.get("rating_mw", 0), 1),
            "combined_risk": round(risk, 2),
            "low_confidence": match_type == "proximity" and float(distance_km) > 20,
        })

    # Sort by combined risk descending, take top N
    hotspots.sort(key=lambda x: -x["combined_risk"])
    result = hotspots[:top_n]

    logger.info(
        f"Substation hotspots: top {len(result)} of {len(hotspots)} "
        f"(max risk={result[0]['combined_risk']:.2f})" if result else "No hotspots"
    )

    return result
