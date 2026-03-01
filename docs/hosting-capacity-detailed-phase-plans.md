# Hosting Capacity Integration: Detailed Phase Plans

Each phase below is implementation-ready with exact file paths, code patterns from the existing codebase, and specific field/method signatures.

---

## Phase 1: Database Schema

### 1.1 Create `app/models/utility.py`

Follow the pattern in `app/models/substation.py` (SQLAlchemy 2.0 `mapped_column` style, imports from `.base`).

```python
class Utility(Base):
    __tablename__ = "utilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_code: Mapped[str] = mapped_column(String(50), unique=True)     # "pge", "pepco", "comed"
    utility_name: Mapped[str] = mapped_column(String(200))
    parent_company: Mapped[Optional[str]] = mapped_column(String(200))     # "Exelon", null
    iso_id: Mapped[Optional[int]] = mapped_column(ForeignKey("isos.id"))
    states: Mapped[Optional[list]] = mapped_column(JSON)                   # ["CA"], ["MD","DC"]
    data_source_type: Mapped[str] = mapped_column(String(50))              # arcgis_feature, arcgis_map, custom, unavailable
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=False)
    service_url: Mapped[Optional[str]] = mapped_column(String(500))
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    config_json: Mapped[Optional[dict]] = mapped_column(JSON)              # full YAML config cached here

    # Relationships
    iso: Mapped[Optional["ISO"]] = relationship()
    hosting_capacity_records: Mapped[list["HostingCapacityRecord"]] = relationship(back_populates="utility")
    ingestion_runs: Mapped[list["HCIngestionRun"]] = relationship(back_populates="utility")
```

### 1.2 Create `app/models/hosting_capacity.py`

Three models in one file:

**`HCIngestionRun`** (audit trail, follows `PipelineRun` pattern from `app/models/pipeline_run.py`):
```python
class HCIngestionRun(Base):
    __tablename__ = "hc_ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")     # running, completed, failed
    records_fetched: Mapped[Optional[int]] = mapped_column(Integer)
    records_written: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))

    utility: Mapped["Utility"] = relationship(back_populates="ingestion_runs")
```

**`HostingCapacityRecord`** (core data, one row per feeder per ingestion):
```python
class HostingCapacityRecord(Base):
    __tablename__ = "hosting_capacity_records"
    __table_args__ = (
        UniqueConstraint("utility_id", "feeder_id_external", "ingestion_run_id", name="uq_hc_record"),
        Index("ix_hc_utility", "utility_id"),
        Index("ix_hc_centroid", "centroid_lat", "centroid_lon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"))
    ingestion_run_id: Mapped[int] = mapped_column(ForeignKey("hc_ingestion_runs.id"))

    # Feeder identification (from utility's data)
    feeder_id_external: Mapped[str] = mapped_column(String(200))
    feeder_name: Mapped[Optional[str]] = mapped_column(String(300))
    substation_name: Mapped[Optional[str]] = mapped_column(String(300))

    # Optional link to existing physical hierarchy (populated by spatial matching)
    substation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("substations.id"))
    feeder_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeders.id"))

    # Canonical capacity fields (normalized to MW)
    hosting_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)
    hosting_capacity_min_mw: Mapped[Optional[float]] = mapped_column(Float)
    hosting_capacity_max_mw: Mapped[Optional[float]] = mapped_column(Float)
    installed_dg_mw: Mapped[Optional[float]] = mapped_column(Float)
    queued_dg_mw: Mapped[Optional[float]] = mapped_column(Float)
    remaining_capacity_mw: Mapped[Optional[float]] = mapped_column(Float)

    # Constraint info
    constraining_metric: Mapped[Optional[str]] = mapped_column(String(100))  # thermal, voltage, protection, islanding

    # Feeder characteristics
    voltage_kv: Mapped[Optional[float]] = mapped_column(Float)
    phase_config: Mapped[Optional[str]] = mapped_column(String(20))         # 3-phase, single-phase, 2-phase
    is_overhead: Mapped[Optional[bool]] = mapped_column(Boolean)
    is_network: Mapped[Optional[bool]] = mapped_column(Boolean)             # network vs radial

    # Geometry
    geometry_type: Mapped[Optional[str]] = mapped_column(String(20))        # Point, MultiLineString, Polygon
    geometry_json: Mapped[Optional[dict]] = mapped_column(JSON)
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float)

    # Provenance
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    raw_attributes: Mapped[Optional[dict]] = mapped_column(JSON)            # original unmodified fields

    # Relationships
    utility: Mapped["Utility"] = relationship(back_populates="hosting_capacity_records")
    ingestion_run: Mapped["HCIngestionRun"] = relationship()
```

**`HostingCapacitySummary`** (pre-aggregated for fast API responses):
```python
class HostingCapacitySummary(Base):
    __tablename__ = "hosting_capacity_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[int] = mapped_column(ForeignKey("utilities.id"), unique=True)
    total_feeders: Mapped[int] = mapped_column(Integer, default=0)
    total_hosting_capacity_mw: Mapped[float] = mapped_column(Float, default=0.0)
    total_installed_dg_mw: Mapped[float] = mapped_column(Float, default=0.0)
    total_remaining_capacity_mw: Mapped[float] = mapped_column(Float, default=0.0)
    avg_utilization_pct: Mapped[Optional[float]] = mapped_column(Float)
    constrained_feeders_count: Mapped[int] = mapped_column(Integer, default=0)
    constraint_breakdown: Mapped[Optional[dict]] = mapped_column(JSON)      # {"thermal": 42, "voltage": 18}
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

### 1.3 Update `app/models/__init__.py`

Add imports and __all__ entries for `Utility`, `HCIngestionRun`, `HostingCapacityRecord`, `HostingCapacitySummary`.

### 1.4 Alembic migration

Follow pattern from `alembic/versions/00810fa89676_add_substation_load_profiles_table.py`:

- Filename: `{hash}_add_hosting_capacity_tables.py`
- `down_revision = '00810fa89676'`
- Creates 4 tables: `utilities`, `hc_ingestion_runs`, `hosting_capacity_records`, `hosting_capacity_summaries`
- Includes unique constraints and indexes as specified in models

### 1.5 Verification

```bash
alembic upgrade head
# Confirm 4 new tables exist:
docker-compose exec db psql -U postgres -d grid_constraint -c "\dt *hosting*; \dt utilities;"
```

---

## Phase 2: ArcGIS REST Client Library

### 2.1 Create `adapters/arcgis_client.py`

Extract and generalize from `scraping/grip_fetcher.py` (lines 50-155). The existing code has the exact pagination loop, coordinate conversion, and error handling to reuse.

```python
"""
Reusable ArcGIS REST API client.

Extracted from scraping/grip_fetcher.py to support hosting capacity
data ingestion across ~50 utility ArcGIS endpoints.
"""

import logging
import math
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class ArcGISClient:
    """Generic ArcGIS FeatureServer/MapServer query client with pagination."""

    def __init__(
        self,
        user_agent: str = "grid-constraint-classifier/2.0",
        rate_limit_sec: float = 0.5,
        max_retries: int = 3,
        timeout: int = 120,
    ):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.rate_limit_sec = rate_limit_sec
        self.max_retries = max_retries
        self.timeout = timeout

    def query_features(
        self,
        url: str,
        where: str = "1=1",
        out_fields: str = "*",
        return_geometry: bool = True,
        out_sr: int = 4326,
        page_size: int = 2000,
        max_records: Optional[int] = None,
        auth_token: Optional[str] = None,
    ) -> list[dict]:
        """
        Paginated feature query. Returns list of raw feature dicts.

        Pagination pattern extracted from grip_fetcher.py lines 82-112.
        Adds: retry with backoff, rate limiting, auth token, outSR reprojection.
        """
        all_features = []
        offset = 0

        while True:
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": str(return_geometry).lower(),
                "outSR": out_sr,
                "f": "json",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            }
            if auth_token:
                params["token"] = auth_token

            data = self._request_with_retry(url, params)
            if data is None:
                break

            features = data.get("features", [])
            if not features:
                break

            all_features.extend(features)
            logger.info(f"  Fetched {len(all_features)} features (offset {offset})...")

            if max_records and len(all_features) >= max_records:
                all_features = all_features[:max_records]
                break

            # Check if more pages exist
            exceeded = data.get("exceededTransferLimit", False)
            if len(features) < page_size and not exceeded:
                break
            offset += page_size

            time.sleep(self.rate_limit_sec)

        return all_features

    def query_features_geojson(self, url: str, **kwargs) -> dict:
        """Query and return as GeoJSON FeatureCollection."""
        features = self.query_features(url, **kwargs)
        geojson_features = []
        for feat in features:
            geom = feat.get("geometry")
            attrs = feat.get("attributes", {})
            geojson_features.append({
                "type": "Feature",
                "properties": attrs,
                "geometry": self._esri_to_geojson_geometry(geom) if geom else None,
            })
        return {"type": "FeatureCollection", "features": geojson_features}

    def discover_layers(self, service_url: str) -> list[dict]:
        """Hit service_url?f=json to list available layers."""
        data = self._request_with_retry(service_url, {"f": "json"})
        if not data:
            return []
        layers = data.get("layers", [])
        tables = data.get("tables", [])
        return [{"id": l["id"], "name": l["name"], "type": "layer"} for l in layers] + \
               [{"id": t["id"], "name": t["name"], "type": "table"} for t in tables]

    def get_field_schema(self, layer_url: str) -> list[dict]:
        """Get field definitions for a specific layer."""
        data = self._request_with_retry(layer_url, {"f": "json"})
        if not data:
            return []
        return data.get("fields", [])

    def get_record_count(self, url: str, where: str = "1=1") -> int:
        """Get total record count for a layer."""
        data = self._request_with_retry(url, {
            "where": where, "returnCountOnly": "true", "f": "json"
        })
        return data.get("count", 0) if data else 0

    def _request_with_retry(self, url: str, params: dict) -> Optional[dict]:
        """HTTP GET with exponential backoff retry."""
        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                # Check for ArcGIS error responses
                if "error" in data:
                    err = data["error"]
                    logger.warning(f"ArcGIS error: {err.get('message', err)}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                return data
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout (attempt {attempt + 1}/{self.max_retries})")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    @staticmethod
    def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
        """Convert Web Mercator (EPSG:3857) to WGS84. From grip_fetcher.py line 50."""
        lon = x / 20037508.34 * 180.0
        lat = math.atan(math.exp(y / 20037508.34 * math.pi)) * 360.0 / math.pi - 90.0
        return lat, lon

    @staticmethod
    def compute_centroid(geometry: dict) -> tuple[Optional[float], Optional[float]]:
        """Compute centroid lat/lon from ArcGIS or GeoJSON geometry."""
        if not geometry:
            return None, None

        # ArcGIS point geometry
        if "x" in geometry and "y" in geometry:
            return geometry["y"], geometry["x"]

        # ArcGIS polyline (paths) or polygon (rings)
        coords = []
        for key in ["paths", "rings"]:
            for ring_or_path in geometry.get(key, []):
                coords.extend(ring_or_path)

        # GeoJSON coordinates
        if "coordinates" in geometry:
            gtype = geometry.get("type", "")
            if gtype == "Point":
                c = geometry["coordinates"]
                return c[1], c[0]  # GeoJSON is [lon, lat]
            elif gtype in ("LineString", "MultiPoint"):
                coords = geometry["coordinates"]
            elif gtype in ("Polygon", "MultiLineString"):
                for ring in geometry["coordinates"]:
                    coords.extend(ring)
            elif gtype == "MultiPolygon":
                for poly in geometry["coordinates"]:
                    for ring in poly:
                        coords.extend(ring)

        if not coords:
            return None, None

        # Average all coordinate points
        if isinstance(coords[0], (list, tuple)) and len(coords[0]) >= 2:
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            return sum(lats) / len(lats), sum(lons) / len(lons)

        return None, None

    @staticmethod
    def _esri_to_geojson_geometry(geom: dict) -> Optional[dict]:
        """Convert ESRI JSON geometry to GeoJSON geometry."""
        if not geom:
            return None
        if "x" in geom and "y" in geom:
            return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
        if "paths" in geom:
            paths = geom["paths"]
            if len(paths) == 1:
                return {"type": "LineString", "coordinates": paths[0]}
            return {"type": "MultiLineString", "coordinates": paths}
        if "rings" in geom:
            return {"type": "Polygon", "coordinates": geom["rings"]}
        return None
```

### 2.2 Refactor `scraping/grip_fetcher.py`

Replace the three manual pagination loops (lines 82-112, 187-212, 294-322) with calls to the new `ArcGISClient`. Keep the same public function signatures (`fetch_grip_substations`, `fetch_substation_load_profiles`, `fetch_division_boundaries`) so no callers break.

### 2.3 Verification

```python
# Quick smoke test
from adapters.arcgis_client import ArcGISClient
client = ArcGISClient()
layers = client.discover_layers(
    "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/DRPComplianceRelProd/FeatureServer"
)
print(f"PG&E GRIP: {len(layers)} layers")

# Fetch 1 page
features = client.query_features(
    "https://services2.arcgis.com/mJaJSax0KPHoCNB6/ArcGIS/rest/services/DRPComplianceRelProd/FeatureServer/7/query",
    page_size=5, max_records=5,
)
print(f"Got {len(features)} features, fields: {list(features[0]['attributes'].keys())}")
```

---

## Phase 3: Utility Adapter + Config System

### 3.1 Create `adapters/hosting_capacity/__init__.py`

Empty init.

### 3.2 Create `adapters/hosting_capacity/base.py`

Follow pattern from `adapters/base.py` (ISOConfig dataclass + ISOAdapter ABC):

```python
@dataclass
class UtilityHCConfig:
    utility_code: str
    utility_name: str
    parent_company: Optional[str]
    iso_id: str
    states: list[str]
    data_source_type: str          # arcgis_feature, arcgis_map, custom, unavailable
    requires_auth: bool

    # ArcGIS endpoint config
    service_url: Optional[str] = None
    layer_index: Optional[int] = None
    page_size: int = 2000
    out_sr: int = 4326

    # Field mapping: utility field name -> canonical field name
    field_map: dict[str, str] = field(default_factory=dict)

    # Unit config
    capacity_unit: str = "kw"      # "kw" or "mw"

    # URL discovery (for ComEd quarterly rotation)
    url_discovery_method: str = "static"   # static, quarterly_name, service_catalog
    url_pattern: Optional[str] = None

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "UtilityHCConfig":
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class HostingCapacityAdapter(ABC):
    def __init__(self, config: UtilityHCConfig, data_dir: Path, arcgis_client: ArcGISClient):
        self.config = config
        self.data_dir = data_dir / "hosting_capacity" / config.utility_code
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = arcgis_client

    @abstractmethod
    def pull_hosting_capacity(self, force: bool = False) -> pd.DataFrame:
        """Pull and normalize hosting capacity data. Returns canonical DataFrame."""
        ...

    def get_cache_path(self) -> Path:
        return self.data_dir / "hosting_capacity.parquet"

    def resolve_current_url(self) -> str:
        """Build the query URL from config. Override for dynamic discovery."""
        return f"{self.config.service_url}/{self.config.layer_index}/query"
```

### 3.3 Create `adapters/hosting_capacity/arcgis_adapter.py`

Generic adapter for public ArcGIS FeatureServer endpoints (covers ~60% of utilities):

```python
class ArcGISHostingCapacityAdapter(HostingCapacityAdapter):

    def pull_hosting_capacity(self, force: bool = False) -> pd.DataFrame:
        cache = self.get_cache_path()
        if cache.exists() and not force:
            logger.info(f"Loading cached HC data for {self.config.utility_code}")
            return pd.read_parquet(cache)

        url = self.resolve_current_url()
        logger.info(f"Fetching HC data for {self.config.utility_code} from {url}")

        features = self.client.query_features(
            url=url,
            page_size=self.config.page_size,
            out_sr=self.config.out_sr,
        )

        if not features:
            logger.warning(f"No features returned for {self.config.utility_code}")
            return pd.DataFrame()

        df = self._features_to_dataframe(features)
        df = normalize_hosting_capacity(df, self.config)  # from normalizer.py

        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
        logger.info(f"Cached {len(df)} HC records for {self.config.utility_code}")
        return df

    def _features_to_dataframe(self, features: list[dict]) -> pd.DataFrame:
        """Convert raw ArcGIS features to DataFrame with geometry."""
        records = []
        for feat in features:
            attrs = feat.get("attributes", {})
            geom = feat.get("geometry")

            row = dict(attrs)
            if geom:
                row["_geometry"] = geom
                row["_geometry_type"] = self._detect_geometry_type(geom)
                lat, lon = ArcGISClient.compute_centroid(geom)
                row["_centroid_lat"] = round(lat, 6) if lat else None
                row["_centroid_lon"] = round(lon, 6) if lon else None

            records.append(row)

        return pd.DataFrame(records)

    @staticmethod
    def _detect_geometry_type(geom: dict) -> str:
        if "x" in geom: return "Point"
        if "paths" in geom: return "MultiLineString"
        if "rings" in geom: return "Polygon"
        return geom.get("type", "Unknown")
```

### 3.4 Create `adapters/hosting_capacity/exelon_adapter.py`

Extends `ArcGISHostingCapacityAdapter` for the 6 Exelon utilities that share org `agWTKEK7X5K1Bx7o`:

- Handles ComEd's quarterly URL rotation via `url_discovery_method: quarterly_name`
- `_resolve_quarterly_url()`: tries current quarter name (e.g. `ComEd_PV_Hosting_Capacity_MAR2026`), falls back to previous quarters
- Discovery: queries `https://services3.arcgis.com/agWTKEK7X5K1Bx7o/arcgis/rest/services?f=json` to find current service name matching pattern

### 3.5 Create `adapters/hosting_capacity/registry.py`

Factory function following the same pattern as the ISO adapter registry:

```python
CONFIGS_DIR = Path(__file__).parent / "configs"
_ADAPTER_MAP = {
    "arcgis_feature": ArcGISHostingCapacityAdapter,
    "arcgis_map": ArcGISHostingCapacityAdapter,       # same client, MapServer URLs
    "exelon": ExelonHostingCapacityAdapter,
}

def get_hc_adapter(utility_code: str, data_dir: Path = None) -> HostingCapacityAdapter:
    config_path = CONFIGS_DIR / f"{utility_code}.yaml"
    config = UtilityHCConfig.from_yaml(config_path)
    adapter_cls = _ADAPTER_MAP.get(config.data_source_type, ArcGISHostingCapacityAdapter)
    client = ArcGISClient()
    return adapter_cls(config, data_dir or Path("data"), client)

def list_hc_utilities() -> list[str]:
    return sorted(p.stem for p in CONFIGS_DIR.glob("*.yaml"))
```

### 3.6 Create YAML configs for Wave 1-3 utilities

**Directory:** `adapters/hosting_capacity/configs/`

Initial configs to create (8 files):

| File | Utility | Key Details |
|------|---------|-------------|
| `pge.yaml` | PG&E | Layer 7 (ICAEstimatedCapacitySummary), 2000/page, kW |
| `sce.yaml` | SCE | drpep.sce.com self-hosted, ICA_Layer, kW |
| `pepco.yaml` | Pepco | PHI shared FS, Layer 0 (PEPCO), 3500/page, kW |
| `bge.yaml` | BGE | Grid-based polygons, Layer 38 (quarter-mile), 1000/page, kW |
| `ace.yaml` | ACE | PHI shared FS, Layer 4 (ACE), 3500/page, kW |
| `dpl.yaml` | Delmarva | PHI shared FS, Layer 2 (DPL), 3500/page, kW |
| `comed.yaml` | ComEd | Quarterly URL rotation, exelon adapter, kW |
| `dominion.yaml` | Dominion | Layer 6 (Primary_HostingCapacity_Final), 2000/page, kW |

Each config file is ~25 lines. The `field_map` section is specific to each utility's schema (discovered via `--discover` mode).

### 3.7 Verification

```bash
python -c "from adapters.hosting_capacity.registry import list_hc_utilities; print(list_hc_utilities())"
# Should print: ['ace', 'bge', 'comed', 'dominion', 'dpl', 'pge', 'pepco', 'sce']
```

---

## Phase 4: Normalization Pipeline

### 4.1 Create `adapters/hosting_capacity/normalizer.py`

Follows the candidate-list pattern from `adapters/gridstatus_adapter.py` `_normalize_zone_lmps()` (lines 64-119):

```python
# Canonical output columns
CANONICAL_COLUMNS = [
    "feeder_id_external", "feeder_name", "substation_name",
    "hosting_capacity_mw", "hosting_capacity_min_mw", "hosting_capacity_max_mw",
    "installed_dg_mw", "queued_dg_mw", "remaining_capacity_mw",
    "constraining_metric", "voltage_kv", "phase_config",
    "is_overhead", "is_network",
    "geometry_type", "geometry_json", "centroid_lat", "centroid_lon",
    "record_date", "raw_attributes",
]

CONSTRAINT_MAP = {
    # Thermal variants
    "thermal": "thermal", "thermal limit": "thermal", "thermal_discharging": "thermal",
    "overload": "thermal", "conductor thermal": "thermal",
    # Voltage variants
    "voltage": "voltage", "voltage rise": "voltage", "primary_over_voltage": "voltage",
    "voltage_deviation": "voltage", "regulator_deviation": "voltage",
    "steady state voltage": "voltage", "voltage variation": "voltage",
    # Protection variants
    "protection": "protection", "fault current": "protection",
    "additional_element_fault": "protection", "breaker_reach": "protection",
    "sympathetic trip": "protection",
    # Islanding variants
    "islanding": "islanding", "unintentional_islanding": "islanding",
    "anti-islanding": "islanding",
    # Reverse power
    "reverse power": "reverse_power", "backfeed": "reverse_power",
}

def normalize_hosting_capacity(df: pd.DataFrame, config: UtilityHCConfig) -> pd.DataFrame:
    """Full normalization pipeline."""
    df = df.copy()

    # 1. Save raw attributes before any transformation
    df["raw_attributes"] = df.apply(lambda row: row.to_dict(), axis=1)

    # 2. Apply field_map renaming
    rename_map = {}
    for src_field, dst_field in config.field_map.items():
        if src_field in df.columns:
            rename_map[src_field] = dst_field
    df = df.rename(columns=rename_map)

    # 3. Unit conversion (kW -> MW)
    if config.capacity_unit == "kw":
        mw_cols = [c for c in [
            "hosting_capacity_mw", "hosting_capacity_min_mw", "hosting_capacity_max_mw",
            "installed_dg_mw", "queued_dg_mw", "remaining_capacity_mw",
        ] if c in df.columns]
        for col in mw_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce") / 1000.0

    # 4. Normalize constraint names
    if "constraining_metric" in df.columns:
        df["constraining_metric"] = (
            df["constraining_metric"]
            .fillna("")
            .str.strip()
            .str.lower()
            .map(lambda v: CONSTRAINT_MAP.get(v, v if v else None))
        )

    # 5. Compute remaining capacity if not present
    if "remaining_capacity_mw" not in df.columns or df["remaining_capacity_mw"].isna().all():
        if "hosting_capacity_mw" in df.columns:
            installed = df.get("installed_dg_mw", 0).fillna(0)
            queued = df.get("queued_dg_mw", 0).fillna(0)
            df["remaining_capacity_mw"] = df["hosting_capacity_mw"] - installed - queued

    # 6. Extract centroids from geometry (if adapter didn't already)
    if "_centroid_lat" in df.columns:
        df["centroid_lat"] = df["_centroid_lat"]
        df["centroid_lon"] = df["_centroid_lon"]
        df["geometry_type"] = df.get("_geometry_type")

    # 7. Validation: require feeder_id_external
    before = len(df)
    df = df.dropna(subset=["feeder_id_external"])
    if len(df) < before:
        logger.warning(f"Dropped {before - len(df)} rows missing feeder_id_external")

    return df
```

### 4.2 Verification

```python
# Test with synthetic data
from adapters.hosting_capacity.normalizer import normalize_hosting_capacity
import pandas as pd

test_df = pd.DataFrame([{
    "FeederId": "F-001", "Allowable_PV_kW": 5000, "Existing_Gen_kW": 1200,
    "Limiting_Factor": "Thermal", "_centroid_lat": 37.78, "_centroid_lon": -122.42,
}])
config = UtilityHCConfig(utility_code="test", ..., capacity_unit="kw",
    field_map={"FeederId": "feeder_id_external", "Allowable_PV_kW": "hosting_capacity_mw",
               "Existing_Gen_kW": "installed_dg_mw", "Limiting_Factor": "constraining_metric"})

result = normalize_hosting_capacity(test_df, config)
assert result["hosting_capacity_mw"].iloc[0] == 5.0   # kW -> MW
assert result["installed_dg_mw"].iloc[0] == 1.2
assert result["remaining_capacity_mw"].iloc[0] == 3.8  # 5.0 - 1.2
assert result["constraining_metric"].iloc[0] == "thermal"
```

---

## Phase 5: CLI Ingestion Command + DB Writer

### 5.1 Create `app/hc_writer.py`

Follow `app/pipeline_writer.py` patterns (lazy DB session, batch insert, run lifecycle):

```python
class HostingCapacityWriter:
    def __init__(self):
        self._db: Optional[Session] = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def close(self):
        if self._db:
            self._db.close()

    def ensure_utility(self, config: UtilityHCConfig) -> Utility:
        """Get or create utility record."""
        util = self.db.query(Utility).filter(Utility.utility_code == config.utility_code).first()
        if not util:
            iso = self.db.query(ISO).filter(ISO.iso_code == config.iso_id).first()
            util = Utility(
                utility_code=config.utility_code,
                utility_name=config.utility_name,
                parent_company=config.parent_company,
                iso_id=iso.id if iso else None,
                states=config.states,
                data_source_type=config.data_source_type,
                requires_auth=config.requires_auth,
                service_url=config.service_url,
            )
            self.db.add(util)
            self.db.flush()
        return util

    def start_run(self, utility: Utility, source_url: str) -> HCIngestionRun:
        """Create ingestion run record."""
        run = HCIngestionRun(
            utility_id=utility.id,
            started_at=datetime.now(timezone.utc),
            status="running",
            source_url=source_url,
        )
        self.db.add(run)
        self.db.commit()
        return run

    def write_records(self, df: pd.DataFrame, utility: Utility, run: HCIngestionRun, batch_size: int = 2000):
        """Batch-insert hosting capacity records. Follows PipelineWriter.write_zone_lmps pattern."""
        # Clear previous records for this utility (latest-wins strategy)
        self.db.query(HostingCapacityRecord).filter(
            HostingCapacityRecord.utility_id == utility.id,
            HostingCapacityRecord.ingestion_run_id != run.id,
        ).delete()
        self.db.commit()

        count = 0
        batch = []
        for _, row in df.iterrows():
            record = HostingCapacityRecord(
                utility_id=utility.id,
                ingestion_run_id=run.id,
                feeder_id_external=row["feeder_id_external"],
                feeder_name=row.get("feeder_name"),
                substation_name=row.get("substation_name"),
                hosting_capacity_mw=row.get("hosting_capacity_mw"),
                hosting_capacity_min_mw=row.get("hosting_capacity_min_mw"),
                hosting_capacity_max_mw=row.get("hosting_capacity_max_mw"),
                installed_dg_mw=row.get("installed_dg_mw"),
                queued_dg_mw=row.get("queued_dg_mw"),
                remaining_capacity_mw=row.get("remaining_capacity_mw"),
                constraining_metric=row.get("constraining_metric"),
                voltage_kv=row.get("voltage_kv"),
                phase_config=row.get("phase_config"),
                is_overhead=row.get("is_overhead"),
                is_network=row.get("is_network"),
                geometry_type=row.get("geometry_type"),
                centroid_lat=row.get("centroid_lat"),
                centroid_lon=row.get("centroid_lon"),
                raw_attributes=row.get("raw_attributes"),
            )
            batch.append(record)
            count += 1

            if len(batch) >= batch_size:
                self.db.bulk_save_objects(batch)
                self.db.commit()
                batch = []

        if batch:
            self.db.bulk_save_objects(batch)
            self.db.commit()

        run.records_written = count
        utility.last_ingested_at = datetime.now(timezone.utc)
        self.db.commit()
        return count

    def compute_summary(self, utility: Utility):
        """Compute and upsert HostingCapacitySummary for a utility."""
        records = self.db.query(HostingCapacityRecord).filter(
            HostingCapacityRecord.utility_id == utility.id
        ).all()

        total_hc = sum(r.hosting_capacity_mw or 0 for r in records)
        total_dg = sum(r.installed_dg_mw or 0 for r in records)
        total_remaining = sum(r.remaining_capacity_mw or 0 for r in records)
        constrained = sum(1 for r in records if (r.remaining_capacity_mw or float('inf')) < 1.0)

        # Constraint breakdown
        breakdown = {}
        for r in records:
            if r.constraining_metric:
                breakdown[r.constraining_metric] = breakdown.get(r.constraining_metric, 0) + 1

        summary = self.db.query(HostingCapacitySummary).filter(
            HostingCapacitySummary.utility_id == utility.id
        ).first()
        if not summary:
            summary = HostingCapacitySummary(utility_id=utility.id)
            self.db.add(summary)

        summary.total_feeders = len(records)
        summary.total_hosting_capacity_mw = round(total_hc, 2)
        summary.total_installed_dg_mw = round(total_dg, 2)
        summary.total_remaining_capacity_mw = round(total_remaining, 2)
        summary.constrained_feeders_count = constrained
        summary.constraint_breakdown = breakdown
        summary.computed_at = datetime.now(timezone.utc)

        self.db.commit()

    def complete_run(self, run: HCIngestionRun, error: Optional[str] = None):
        """Mark run as completed or failed. Follows PipelineWriter.complete_run pattern."""
        run.completed_at = datetime.now(timezone.utc)
        run.status = "failed" if error else "completed"
        if error:
            run.error_message = str(error)[:1000]
        self.db.commit()
```

### 5.2 Create `cli/ingest_hosting_capacity.py`

```python
"""
Utility Hosting Capacity Ingestion CLI.

Usage:
  python -m cli.ingest_hosting_capacity --utility pge
  python -m cli.ingest_hosting_capacity --utility all
  python -m cli.ingest_hosting_capacity --utility all --category arcgis_feature
  python -m cli.ingest_hosting_capacity --utility pge --force
  python -m cli.ingest_hosting_capacity --utility pge --dry-run
  python -m cli.ingest_hosting_capacity --list-utilities
  python -m cli.ingest_hosting_capacity --utility pge --discover
"""

import argparse, logging, sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Ingest utility hosting capacity data")
    parser.add_argument("--utility", help="Utility code or 'all'")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + normalize only, no DB write")
    parser.add_argument("--list-utilities", action="store_true")
    parser.add_argument("--discover", action="store_true", help="Discover layers and fields")
    parser.add_argument("--category", help="Filter by data_source_type")
    parser.add_argument("--data-dir", default="data", type=Path)
    args = parser.parse_args()

    if args.list_utilities:
        # Print table of configured utilities with status
        ...

    if args.discover:
        # Use ArcGIS client to discover layers and print field schemas
        ...

    if args.utility == "all":
        utilities = list_hc_utilities()
        if args.category:
            utilities = [u for u in utilities if get_config(u).data_source_type == args.category]
        results = {}
        for code in utilities:
            results[code] = ingest_single(code, args)
        # Print summary table
    else:
        ingest_single(args.utility, args)


def ingest_single(utility_code: str, args) -> dict:
    adapter = get_hc_adapter(utility_code, data_dir=args.data_dir)
    logger.info(f"=== Ingesting {adapter.config.utility_name} ({utility_code}) ===")

    # Fetch + normalize
    df = adapter.pull_hosting_capacity(force=args.force)
    logger.info(f"Fetched {len(df)} records")

    if args.dry_run:
        # Print sample and stats
        return {"records": len(df), "status": "dry_run"}

    # DB write
    writer = HostingCapacityWriter()
    try:
        utility = writer.ensure_utility(adapter.config)
        run = writer.start_run(utility, adapter.resolve_current_url())
        run.records_fetched = len(df)

        count = writer.write_records(df, utility, run)
        writer.compute_summary(utility)
        writer.complete_run(run)
        logger.info(f"Wrote {count} records to DB")
        return {"records": count, "status": "completed"}
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        if 'run' in locals():
            writer.complete_run(run, error=str(e))
        return {"records": 0, "status": "failed", "error": str(e)}
    finally:
        writer.close()
```

### 5.3 Verification

```bash
# Discover PG&E layers
python -m cli.ingest_hosting_capacity --utility pge --discover

# Dry run
python -m cli.ingest_hosting_capacity --utility pge --dry-run

# Full ingestion
python -m cli.ingest_hosting_capacity --utility pge

# Check results
python -m cli.ingest_hosting_capacity --list-utilities
```

---

## Phase 6: API Endpoints

### 6.1 Create `app/schemas/hosting_capacity_schemas.py`

Follow pattern from `app/schemas/responses.py`:

```python
class UtilityResponse(BaseModel):
    utility_code: str
    utility_name: str
    parent_company: Optional[str] = None
    iso_code: Optional[str] = None
    states: Optional[list] = None
    data_source_type: str
    last_ingested_at: Optional[datetime] = None
    total_feeders: Optional[int] = None
    total_remaining_capacity_mw: Optional[float] = None

class HostingCapacityResponse(BaseModel):
    id: int
    utility_code: str
    feeder_id_external: str
    feeder_name: Optional[str] = None
    substation_name: Optional[str] = None
    hosting_capacity_mw: Optional[float] = None
    remaining_capacity_mw: Optional[float] = None
    installed_dg_mw: Optional[float] = None
    constraining_metric: Optional[str] = None
    voltage_kv: Optional[float] = None
    centroid_lat: Optional[float] = None
    centroid_lon: Optional[float] = None

class HCSummaryResponse(BaseModel):
    utility_code: str
    utility_name: str
    total_feeders: int
    total_hosting_capacity_mw: float
    total_installed_dg_mw: float
    total_remaining_capacity_mw: float
    constrained_feeders_count: int
    constraint_breakdown: Optional[dict] = None
    computed_at: Optional[datetime] = None

class HCIngestionRunResponse(BaseModel):
    id: int
    utility_code: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    records_fetched: Optional[int] = None
    records_written: Optional[int] = None
    error_message: Optional[str] = None
```

### 6.2 Create `app/api/v1/hosting_capacity_routes.py`

Follow pattern from `app/api/v1/hierarchy_routes.py`:

7 endpoints as listed in the master plan. Key endpoints:

- `GET /utilities` - joins Utility with HostingCapacitySummary for combined response
- `GET /utilities/{code}/hosting-capacity` - paginates HostingCapacityRecord with bbox filter (`centroid_lat BETWEEN lat1 AND lat2`)
- `GET /utilities/{code}/hosting-capacity/geojson` - builds GeoJSON FeatureCollection server-side
- `GET /hosting-capacity/nearby` - haversine distance query across all utilities

### 6.3 Register router in `app/main.py`

```python
from app.api.v1.hosting_capacity_routes import router as hc_router
app.include_router(hc_router)
```

### 6.4 Verification

```bash
curl http://localhost:8000/api/v1/utilities | python -m json.tool
curl http://localhost:8000/api/v1/utilities/pge/hosting-capacity/summary | python -m json.tool
curl "http://localhost:8000/api/v1/utilities/pge/hosting-capacity?limit=5" | python -m json.tool
curl "http://localhost:8000/api/v1/hosting-capacity/nearby?lat=37.78&lon=-122.42&radius_km=10" | python -m json.tool
```

---

## Phase 7: Frontend Map Layer

### 7.1 Create `frontend/src/api/hostingCapacity.ts`

Follow pattern from `frontend/src/api/hierarchy.ts`:

```typescript
import client from './client'

export interface HCFeeder {
  id: number
  utility_code: string
  feeder_id_external: string
  feeder_name: string | null
  substation_name: string | null
  hosting_capacity_mw: number | null
  remaining_capacity_mw: number | null
  installed_dg_mw: number | null
  constraining_metric: string | null
  voltage_kv: number | null
  centroid_lat: number | null
  centroid_lon: number | null
}

export interface HCUtility {
  utility_code: string
  utility_name: string
  parent_company: string | null
  iso_code: string | null
  states: string[] | null
  total_feeders: number | null
  total_remaining_capacity_mw: number | null
  last_ingested_at: string | null
}

export async function fetchUtilities(): Promise<HCUtility[]> {
  const { data } = await client.get<HCUtility[]>('/utilities')
  return data
}

export async function fetchHostingCapacity(
  utilityCode: string, bbox?: string, limit?: number,
): Promise<HCFeeder[]> {
  const params: Record<string, string | number> = {}
  if (bbox) params.bbox = bbox
  if (limit) params.limit = limit
  const { data } = await client.get<HCFeeder[]>(`/utilities/${utilityCode}/hosting-capacity`, { params })
  return data
}
```

### 7.2 Create `frontend/src/stores/hostingCapacityStore.ts`

Follow pattern from `frontend/src/stores/hierarchyStore.ts`:

```typescript
export const useHostingCapacityStore = defineStore('hostingCapacity', () => {
  const utilities = ref<HCUtility[]>([])
  const feeders = ref<HCFeeder[]>([])
  const selectedUtility = ref<string | null>(null)
  const selectedFeeder = ref<HCFeeder | null>(null)
  const isLoading = ref(false)

  async function loadUtilities() { ... }
  async function loadFeeders(utilityCode: string) { ... }
  async function selectFeeder(feederId: number) { ... }

  return { utilities, feeders, selectedUtility, selectedFeeder, isLoading,
           loadUtilities, loadFeeders, selectFeeder }
})
```

### 7.3 Create `frontend/src/components/map/HostingCapacityLayer.vue`

Follow pattern from `frontend/src/components/map/SubstationMarkers.vue`:

```vue
<template>
  <l-circle-marker
    v-for="f in visibleFeeders"
    :key="f.id"
    :lat-lng="[f.centroid_lat!, f.centroid_lon!]"
    :radius="5"
    :color="capacityColor(f.remaining_capacity_mw)"
    :fill-color="capacityColor(f.remaining_capacity_mw)"
    :fill-opacity="0.7"
    :weight="1"
    @click="onFeederClick(f)"
  >
    <l-popup>
      <div style="font-size: 12px; min-width: 200px;">
        <strong>{{ f.feeder_name || f.feeder_id_external }}</strong><br />
        Hosting: {{ f.hosting_capacity_mw?.toFixed(1) ?? '?' }} MW<br />
        Remaining: {{ f.remaining_capacity_mw?.toFixed(1) ?? '?' }} MW<br />
        Installed DG: {{ f.installed_dg_mw?.toFixed(1) ?? '?' }} MW<br />
        Constraint: {{ f.constraining_metric ?? 'N/A' }}<br />
        Utility: {{ f.utility_code.toUpperCase() }}
      </div>
    </l-popup>
  </l-circle-marker>
</template>

<script setup lang="ts">
function capacityColor(remaining: number | null): string {
  if (remaining == null) return '#95a5a6'
  if (remaining > 5) return '#2ecc71'    // green
  if (remaining > 2) return '#f1c40f'    // yellow
  if (remaining > 0.5) return '#e67e22'  // orange
  return '#e74c3c'                        // red
}
</script>
```

### 7.4 Modify existing files

**`frontend/src/stores/mapStore.ts`**: Add `showHostingCapacity` ref (default false), `selectedHCFeederId` ref.

**`frontend/src/components/map/GridMap.vue`**: Add import and conditional render:
```vue
<HostingCapacityLayer v-if="mapStore.showHostingCapacity" />
```

**`frontend/src/views/DashboardView.vue`**: Add layer toggle checkbox and utility selector dropdown in the layer controls section.

**`frontend/src/components/map/MapLegend.vue`**: Add HC color legend section when `mapStore.showHostingCapacity` is true.

### 7.5 Verification

```bash
cd frontend && npm run dev
# Open localhost:5173, check "Hosting Capacity" checkbox
# Verify markers render at feeder centroids with green/yellow/orange/red colors
# Click a marker to see popup with capacity details
```

---

## Phase 8: Utility Rollout Waves

This phase is about creating YAML config files and validating each utility's data quality.

### Wave 1: PG&E (proof of concept, validates all infrastructure)
- Create `pge.yaml` config
- Run full pipeline: `--discover`, `--dry-run`, then full ingestion
- Validate: record count matches ArcGIS FeatureServer total, centroids fall within CA

### Wave 2: SCE + SDG&E
- SCE: self-hosted ArcGIS at `drpep.sce.com`, test separately
- SDG&E: mark as `data_source_type: unavailable` initially (requires registration)

### Wave 3: Exelon family (6 utilities from 1 org)
- Create configs for Pepco, BGE, ACE, DPL, ComEd
- Test ComEd quarterly URL discovery
- Validate: all 5 PHI utilities normalize to same schema despite different layer indices

### Wave 4: East Coast (Dominion, National Grid, Eversource, Con Edison)
- Dominion: straightforward, 3 fields only
- National Grid: self-hosted MapServer at `systemdataportal.nationalgrid.com`
- Eversource: self-hosted at `epochprodgasdist.eversource.com`
- Con Edison: discover endpoints from ArcGIS Online map JSON

### Wave 5+: Remaining utilities (expand configs as time allows)

### Verification for each wave

```bash
# 1. Discover schema
python -m cli.ingest_hosting_capacity --utility {code} --discover

# 2. Dry run (check normalization)
python -m cli.ingest_hosting_capacity --utility {code} --dry-run

# 3. Full ingestion
python -m cli.ingest_hosting_capacity --utility {code}

# 4. Verify via API
curl http://localhost:8000/api/v1/utilities/{code}/hosting-capacity/summary

# 5. Visual check on map
# Open frontend, select utility, verify markers appear in correct geography
```
