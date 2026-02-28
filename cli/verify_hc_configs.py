"""
Batch verification of hosting capacity YAML configs.

Validates each config by:
  1. Loading the YAML and checking required fields
  2. Probing the ArcGIS endpoint (service metadata + layer existence)
  3. Fetching a small sample (5 records) and checking field_map coverage
  4. Reporting results in a summary table

Usage:
  python -m cli.verify_hc_configs
  python -m cli.verify_hc_configs --utility pge
  python -m cli.verify_hc_configs --category arcgis_feature
  python -m cli.verify_hc_configs --quick  # skip sample fetch
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.arcgis_client import ArcGISClient
from adapters.hosting_capacity.base import UtilityHCConfig
from adapters.hosting_capacity.registry import list_hc_utilities

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "adapters" / "hosting_capacity" / "configs"


def verify_config(config: UtilityHCConfig, client: ArcGISClient, quick: bool = False) -> dict:
    """Verify a single utility config. Returns result dict."""
    result = {
        "code": config.utility_code,
        "name": config.utility_name,
        "type": config.data_source_type,
        "yaml_ok": True,
        "endpoint_ok": None,
        "layer_ok": None,
        "fields_ok": None,
        "sample_ok": None,
        "record_count": None,
        "field_coverage": None,
        "errors": [],
    }

    # 1. YAML validation
    if not config.service_url:
        result["yaml_ok"] = False
        result["errors"].append("missing service_url")
        return result
    if config.layer_index is None:
        result["yaml_ok"] = False
        result["errors"].append("missing layer_index")
        return result
    if not config.field_map:
        result["errors"].append("empty field_map")
    if "feeder_id_external" not in config.field_map.values():
        result["errors"].append("field_map missing feeder_id_external target")

    # Skip endpoint probing for non-ArcGIS types
    if config.data_source_type not in ("arcgis_feature", "arcgis_map", "exelon", "xcel"):
        result["endpoint_ok"] = "skipped"
        return result

    # 2. Probe service endpoint
    try:
        layers = client.discover_layers(config.service_url)
        result["endpoint_ok"] = bool(layers)
        if not layers:
            result["errors"].append("endpoint returned no layers")
            return result
    except Exception as e:
        result["endpoint_ok"] = False
        result["errors"].append(f"endpoint error: {e}")
        return result

    # 3. Check layer exists
    layer_ids = {l["id"] for l in layers}
    if config.layer_index in layer_ids:
        result["layer_ok"] = True
    else:
        result["layer_ok"] = False
        result["errors"].append(f"layer {config.layer_index} not in {sorted(layer_ids)}")
        return result

    if quick:
        return result

    # 4. Fetch small sample and check field coverage
    try:
        query_url = f"{config.service_url}/{config.layer_index}/query"
        count = client.get_record_count(query_url)
        result["record_count"] = count

        features = client.query_features(
            url=query_url,
            page_size=5,
            max_records=5,
            out_sr=config.out_sr,
        )
        if features:
            result["sample_ok"] = True
            # Check field_map coverage
            sample_fields = set(features[0].get("attributes", {}).keys())
            mapped_fields = set(config.field_map.keys())
            missing = mapped_fields - sample_fields
            if missing:
                result["errors"].append(f"field_map refs missing fields: {missing}")
                result["fields_ok"] = False
            else:
                result["fields_ok"] = True
            unmapped = sample_fields - mapped_fields - {"OBJECTID", "FID", "Shape__Area", "Shape__Length", "GlobalID"}
            coverage = len(mapped_fields & sample_fields) / max(len(mapped_fields), 1)
            result["field_coverage"] = f"{coverage:.0%}"
        else:
            result["sample_ok"] = False
            result["errors"].append("sample fetch returned 0 features")
    except Exception as e:
        result["sample_ok"] = False
        result["errors"].append(f"sample error: {e}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Verify HC YAML configs")
    parser.add_argument("--utility", help="Single utility code to verify")
    parser.add_argument("--category", help="Filter by data_source_type")
    parser.add_argument("--quick", action="store_true", help="Skip sample fetch")
    args = parser.parse_args()

    client = ArcGISClient(rate_limit_sec=0.3)

    if args.utility:
        codes = [args.utility]
    else:
        codes = list_hc_utilities()

    if args.category:
        filtered = []
        for code in codes:
            cfg = UtilityHCConfig.from_yaml(CONFIGS_DIR / f"{code}.yaml")
            if cfg.data_source_type == args.category:
                filtered.append(code)
        codes = filtered

    results = []
    for code in codes:
        config_path = CONFIGS_DIR / f"{code}.yaml"
        if not config_path.exists():
            results.append({"code": code, "errors": ["config file not found"]})
            continue
        config = UtilityHCConfig.from_yaml(config_path)
        print(f"  Verifying {code}...", end="", flush=True)
        result = verify_config(config, client, quick=args.quick)
        status = "OK" if not result["errors"] else "WARN" if result.get("endpoint_ok") else "FAIL"
        print(f" {status}")
        results.append(result)

    # Summary table
    print(f"\n{'='*90}")
    print(f"{'Code':<12} {'Type':<16} {'Endpoint':>8} {'Layer':>6} {'Fields':>7} {'Records':>8} {'Status'}")
    print(f"{'-'*90}")

    ok_count = 0
    warn_count = 0
    fail_count = 0

    for r in results:
        endpoint = _status_icon(r.get("endpoint_ok"))
        layer = _status_icon(r.get("layer_ok"))
        fields = r.get("field_coverage") or "-"
        records = str(r.get("record_count")) if r.get("record_count") is not None else "-"
        errors = "; ".join(r.get("errors", []))

        if not errors:
            status = "OK"
            ok_count += 1
        elif r.get("endpoint_ok"):
            status = f"WARN: {errors}"
            warn_count += 1
        else:
            status = f"FAIL: {errors}"
            fail_count += 1

        print(f"{r.get('code', '?'):<12} {r.get('type', '?'):<16} {endpoint:>8} {layer:>6} {fields:>7} {records:>8} {status}")

    print(f"{'='*90}")
    print(f"Total: {len(results)} configs | {ok_count} OK | {warn_count} WARN | {fail_count} FAIL\n")


def _status_icon(val):
    if val is True:
        return "yes"
    elif val is False:
        return "NO"
    elif val == "skipped":
        return "skip"
    return "-"


if __name__ == "__main__":
    main()
