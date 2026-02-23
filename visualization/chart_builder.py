"""
Chart builders for grid constraint classification results.

All chart functions are parameterized for any ISO: titles, RTO aggregates,
and column names are configurable.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

CLASS_COLORS = {
    "transmission": "#e74c3c",
    "generation": "#3498db",
    "both": "#9b59b6",
    "unconstrained": "#2ecc71",
}


def create_score_bar_chart(
    classification_df: pd.DataFrame,
    output_path: Optional[Path] = None,
    iso_name: str = "PJM",
):
    """Bar chart comparing transmission vs generation scores by zone."""
    if output_path is None:
        output_path = Path("output") / "score_comparison.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = classification_df.sort_values("transmission_score", ascending=True)

    fig, ax = plt.subplots(figsize=(12, max(8, len(df) * 0.4)))

    y = np.arange(len(df))
    height = 0.35

    ax.barh(y - height / 2, df["transmission_score"], height,
            label="Transmission Score", color="#e74c3c", alpha=0.8)
    ax.barh(y + height / 2, df["generation_score"], height,
            label="Generation Score", color="#3498db", alpha=0.8)

    ax.set_yticks(y)
    ax.set_yticklabels(df["zone"])
    ax.set_xlabel("Score (0-1)")
    ax.set_title(f"{iso_name} Zone Constraint Scores: Transmission vs Generation")
    ax.axvline(x=0.5, color="gray", linestyle="--", alpha=0.5, label="Threshold (0.5)")
    ax.legend(loc="lower right")

    for i, (_, row) in enumerate(df.iterrows()):
        color = CLASS_COLORS.get(row["classification"], "gray")
        ax.get_yticklabels()[i].set_color(color)
        ax.get_yticklabels()[i].set_fontweight("bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved score comparison chart to {output_path}")


def create_congestion_heatmap(
    lmp_df: pd.DataFrame,
    output_path: Optional[Path] = None,
    rto_aggregates: Optional[set[str]] = None,
    zone_column: str = "pnode_name",
    congestion_column: str = "congestion_price_da",
    iso_name: str = "PJM",
):
    """Heatmap of average congestion by zone x hour-of-day."""
    if output_path is None:
        output_path = Path("output") / "congestion_heatmap.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if rto_aggregates is None:
        rto_aggregates = set()

    zone_df = lmp_df[~lmp_df[zone_column].isin(rto_aggregates)].copy()

    pivot = zone_df.pivot_table(
        values=congestion_column,
        index=zone_column,
        columns="hour",
        aggfunc=lambda x: x.abs().mean(),
    )

    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=True).drop(columns="total")

    fig, ax = plt.subplots(figsize=(14, max(8, len(pivot) * 0.4)))

    im = ax.imshow(
        pivot.values,
        aspect="auto",
        cmap="YlOrRd",
        interpolation="nearest",
    )

    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_xticks(range(24))
    ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=8)
    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Zone")
    ax.set_title(f"{iso_name} Average Absolute Congestion Price by Zone and Hour ($/MWh)")

    plt.colorbar(im, ax=ax, label="$/MWh")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved congestion heatmap to {output_path}")


def create_monthly_trend_chart(
    lmp_df: pd.DataFrame,
    top_n: int = 6,
    output_path: Optional[Path] = None,
    rto_aggregates: Optional[set[str]] = None,
    zone_column: str = "pnode_name",
    congestion_column: str = "congestion_price_da",
    iso_name: str = "PJM",
):
    """Line chart of monthly congestion trends for top N zones."""
    if output_path is None:
        output_path = Path("output") / "monthly_congestion_trends.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if rto_aggregates is None:
        rto_aggregates = set()

    zone_df = lmp_df[~lmp_df[zone_column].isin(rto_aggregates)].copy()

    zone_totals = zone_df.groupby(zone_column)[congestion_column].apply(
        lambda x: x.abs().mean()
    ).nlargest(top_n)

    top_zones = zone_totals.index.tolist()

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.Set1(np.linspace(0, 1, top_n))

    for zone, color in zip(top_zones, colors):
        zdf = zone_df[zone_df[zone_column] == zone]
        monthly = zdf.groupby("month")[congestion_column].apply(
            lambda x: x.abs().mean()
        )
        ax.plot(monthly.index, monthly.values, marker="o", label=zone,
                color=color, linewidth=2)

    ax.set_xlabel("Month")
    ax.set_ylabel("Avg |Congestion| ($/MWh)")
    ax.set_title(f"{iso_name} Monthly Congestion Trends: Top {top_n} Zones")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved monthly trend chart to {output_path}")
