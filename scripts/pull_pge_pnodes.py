"""
Pull August 2025 nodal LMPs for all 856 PG&E territory PNodes.
Saves progress incrementally in batch parquet files.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.caiso_client import CAISOClient

CACHE_DIR = Path("data/caiso/node_lmps")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
FINAL_PATH = CACHE_DIR / "node_lmps_pge_2025_08.parquet"

if FINAL_PATH.exists():
    print(f"Already cached at {FINAL_PATH}")
    df = pd.read_parquet(FINAL_PATH)
    print(f"Shape: {df.shape}, nodes: {df['pnode_name'].nunique()}")
    sys.exit(0)

# Load PNode registry
with open("data/caiso/pge_pnode_registry.json") as f:
    registry = json.load(f)
all_nodes = sorted(registry["np15"] + registry["zp26"])
print(f"Total PG&E PNodes: {len(all_nodes)}")

# Pull in batches of 10 nodes, caching each batch
client = CAISOClient()
BATCH_SIZE = 10
all_frames = []
start_time = time.time()

for i in range(0, len(all_nodes), BATCH_SIZE):
    batch_num = i // BATCH_SIZE + 1
    total_batches = (len(all_nodes) + BATCH_SIZE - 1) // BATCH_SIZE
    batch_nodes = all_nodes[i:i + BATCH_SIZE]

    # Check if this batch is already cached
    batch_path = CACHE_DIR / f"batch_{batch_num:03d}.parquet"
    if batch_path.exists():
        df_batch = pd.read_parquet(batch_path)
        all_frames.append(df_batch)
        print(f"[{batch_num}/{total_batches}] Loaded cached batch: {len(df_batch)} rows")
        continue

    print(f"[{batch_num}/{total_batches}] Pulling {len(batch_nodes)} nodes: {batch_nodes[0]}...{batch_nodes[-1]}")

    df_batch = client.query_lmps("2025-08-01", "2025-08-31", nodes=batch_nodes)

    if len(df_batch) > 0:
        df_batch.to_parquet(batch_path, index=False)
        all_frames.append(df_batch)
        elapsed = time.time() - start_time
        est_remaining = (elapsed / batch_num) * (total_batches - batch_num)
        print(f"  -> {len(df_batch)} rows, {df_batch['pnode_name'].nunique()} nodes | "
              f"elapsed: {elapsed/60:.1f}m, est remaining: {est_remaining/60:.1f}m")
    else:
        print(f"  -> No data returned")

# Combine all batches
if all_frames:
    combined = pd.concat(all_frames, ignore_index=True)
    combined.to_parquet(FINAL_PATH, index=False)

    elapsed = time.time() - start_time
    print(f"\n=== DONE in {elapsed/60:.1f} minutes ===")
    print(f"Shape: {combined.shape}")
    print(f"Unique nodes: {combined['pnode_name'].nunique()}")
    print(f"Date range: {combined['datetime_beginning_ept'].min()} to {combined['datetime_beginning_ept'].max()}")

    # Top congestion nodes
    cong = combined.groupby('pnode_name')['congestion_price_da'].agg(['mean', 'std', 'min', 'max'])
    cong['abs_mean'] = combined.groupby('pnode_name')['congestion_price_da'].apply(lambda x: x.abs().mean())
    top20 = cong.nlargest(20, 'abs_mean')
    print(f"\nTop 20 nodes by avg |congestion|:")
    print(top20[['abs_mean', 'mean', 'min', 'max']].to_string())

    # Clean up batch files
    for f in CACHE_DIR.glob("batch_*.parquet"):
        f.unlink()
    print("\nCleaned up batch files.")
else:
    print("No data retrieved!")
