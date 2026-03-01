"""
California ISO (CAISO) adapter.

Primary source: custom OASIS API client for 23 Sub-LAP LMPs.
Fallback: gridstatus (returns only 3 trading hubs).

PNode support: pulls all PG&E PNodes as a single "PGE_ALL" group
since CAISO has no PNode-to-Sub-LAP mapping (unlike PJM zone filtering).
"""

import calendar
import json
import logging
from pathlib import Path

import pandas as pd

from .base import ISOConfig
from .gridstatus_adapter import GridstatusAdapter

logger = logging.getLogger(__name__)


class CAISOAdapter(GridstatusAdapter):
    """
    CAISO adapter with dual data source support:
      - Primary: custom OASIS API client (23 Sub-LAPs)
      - Fallback: gridstatus (3 trading hubs)
    """

    def __init__(self, config: ISOConfig, data_dir: Path):
        super().__init__(config, data_dir)
        self._caiso_client = None

    def _get_caiso_client(self):
        """Lazy-load the custom CAISO OASIS client."""
        if self._caiso_client is None:
            from src.caiso_client import CAISOClient
            self._caiso_client = CAISOClient()
        return self._caiso_client

    def pull_zone_lmps(self, year: int, force: bool = False) -> pd.DataFrame:
        """Pull CAISO Sub-LAP LMPs, preferring OASIS API over gridstatus."""
        cache_path = self.data_dir / "zone_lmps" / f"zone_lmps_{year}.parquet"

        if cache_path.exists() and not force:
            logger.info(f"Loading cached zone LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        # Try custom OASIS client first
        try:
            return self._pull_zone_lmps_oasis(year, cache_path)
        except Exception as e:
            logger.warning(f"OASIS pull failed ({e}), falling back to gridstatus")
            return super().pull_zone_lmps(year, force=True)

    def _pull_zone_lmps_oasis(
        self, year: int, cache_path: Path
    ) -> pd.DataFrame:
        """Pull Sub-LAP LMPs using the custom OASIS client."""
        client = self._get_caiso_client()
        nodes = list(self.config.zones.keys())

        logger.info(
            f"Pulling CAISO Sub-LAP LMPs for {year} via OASIS "
            f"({len(nodes)} Sub-LAPs)"
        )

        df = client.query_lmps(
            start_date=f"{year}-01-01",
            end_date=f"{year}-12-31",
            nodes=nodes,
        )

        if len(df) == 0:
            logger.warning("No Sub-LAP LMP data returned from OASIS")
            return df

        # Ensure numeric columns
        for col in ["system_energy_price_da", "total_lmp_da",
                     "congestion_price_da", "marginal_loss_price_da"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path, index=False)
        logger.info(f"Cached {len(df)} rows to {cache_path}")

        return df

    # ── PNode-level LMP support ──

    def _load_pnode_registry(self) -> list[str]:
        """Load PG&E PNode names from the registry JSON."""
        registry_path = self.data_dir / "pge_pnode_registry.json"
        if not registry_path.exists():
            raise FileNotFoundError(
                f"PNode registry not found at {registry_path}. "
                "Run scripts/pull_pge_pnodes.py first."
            )
        with open(registry_path) as f:
            registry = json.load(f)
        # Flatten all trading hubs (np15, zp26) into a single list
        # Skip non-list entries like "total" count
        all_pnodes = []
        for hub, nodes in registry.items():
            if isinstance(nodes, list):
                all_pnodes.extend(nodes)
        all_pnodes = sorted(set(all_pnodes))
        logger.info(f"Loaded {len(all_pnodes)} PG&E PNodes from registry")
        return all_pnodes

    def pull_node_lmps(
        self, zone: str, year: int, month: int, force: bool = False
    ) -> pd.DataFrame:
        """
        Pull node-level LMPs for PG&E PNodes for a single month.

        Zone is expected to be "PGE_ALL" (all PG&E PNodes as one group).
        Uses the custom OASIS client in batches of 10 nodes.
        """
        cache_path = (
            self.data_dir / "node_lmps"
            / f"node_lmps_{zone}_{year}_{month:02d}.parquet"
        )

        if cache_path.exists() and not force:
            logger.info(f"Loading cached node LMPs from {cache_path}")
            return pd.read_parquet(cache_path)

        pnodes = self._load_pnode_registry()
        client = self._get_caiso_client()

        last_day = calendar.monthrange(year, month)[1]
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day}"

        logger.info(
            f"Pulling CAISO PNode LMPs for {zone} {year}-{month:02d} "
            f"({len(pnodes)} nodes in batches of 10)"
        )

        # Pull in batches with incremental caching for resume-on-failure
        batch_dir = cache_path.parent / f"_batches_{zone}_{year}_{month:02d}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        batch_size = 10
        frames = []

        for i in range(0, len(pnodes), batch_size):
            batch_idx = i // batch_size
            batch_cache = batch_dir / f"batch_{batch_idx:04d}.parquet"

            if batch_cache.exists() and not force:
                frames.append(pd.read_parquet(batch_cache))
                continue

            batch = pnodes[i : i + batch_size]
            try:
                df = client.query_lmps(
                    start_date=start_date,
                    end_date=end_date,
                    nodes=batch,
                )
                if len(df) > 0:
                    df.to_parquet(batch_cache, index=False)
                    frames.append(df)
            except Exception as e:
                logger.warning(
                    f"Batch {batch_idx} failed ({batch[0]}...): {e}"
                )

        if not frames:
            logger.warning(f"No PNode LMP data for {zone} {year}-{month:02d}")
            return pd.DataFrame()

        combined = pd.concat(frames, ignore_index=True)

        # Add pnode_id (hash-based) since OASIS PNode names lack numeric IDs
        if "pnode_id" not in combined.columns and "pnode_name" in combined.columns:
            combined["pnode_id"] = combined["pnode_name"].apply(
                lambda x: abs(hash(str(x))) % 10**8
            )

        # Ensure numeric columns
        for col in ["total_lmp_da", "congestion_price_da",
                     "marginal_loss_price_da", "system_energy_price_da"]:
            if col in combined.columns:
                combined[col] = pd.to_numeric(combined[col], errors="coerce")

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path, index=False)
        logger.info(
            f"Cached {len(combined)} PNode LMP rows to {cache_path} "
            f"({combined['pnode_name'].nunique()} nodes)"
        )

        # Clean up batch files
        import shutil
        shutil.rmtree(batch_dir, ignore_errors=True)

        return combined

    def pull_constrained_zone_pnodes(
        self,
        classification_summary: dict,
        year: int = 2025,
        force: bool = False,
    ) -> dict:
        """
        Override base method: pull ALL PG&E PNodes as a single "PGE_ALL" group.

        CAISO has no PNode-to-Sub-LAP mapping (ATL_PNODE_MAP only maps to
        trading hubs NP15/ZP26). Instead, we pull all PG&E PNodes and let
        the pnode_analyzer score each individually.

        Only triggers if any PG&E Sub-LAP zone is constrained (T >= 0.5 or G >= 0.5).
        """
        zone_scores = classification_summary.get("zone_scores", [])
        pge_constrained = False
        for zs in zone_scores:
            zone = zs.get("zone", "")
            if not zone.startswith("SLAP_PG"):
                continue
            t = zs.get("transmission_score", 0)
            g = zs.get("generation_score", 0)
            if t >= 0.5 or g >= 0.5:
                pge_constrained = True
                break

        if not pge_constrained:
            logger.info("No PG&E Sub-LAP zones are constrained, skipping PNode drill-down")
            return {}

        logger.info("PG&E Sub-LAP zones constrained, pulling all PG&E PNodes as PGE_ALL")
        node_lmps = self.pull_node_lmps_year(zone="PGE_ALL", year=year, force=force)

        if node_lmps.empty:
            logger.warning("No PNode LMP data returned for PGE_ALL")
            return {}

        return {"PGE_ALL": node_lmps}
