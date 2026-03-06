"""
Seed interconnection queue with representative projects.

Creates realistic interconnection queue entries based on public queue data
patterns from CAISO, PJM, MISO, NYISO, and SPP.

Usage:
  python -m cli.seed_interconnection_queue [--dry-run]
"""

import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Seed for reproducibility
random.seed(42)

# Representative queue data by ISO region
QUEUE_DATA = {
    "caiso": {
        "state": "CA",
        "projects": [
            # Solar projects in Central Valley and desert
            {"name": "Westlands Solar Park Phase IV", "type": "solar", "mw": 400, "lat": 36.25, "lon": -120.05, "status": "active", "poi": "Gates 500kV", "sub": "Gates"},
            {"name": "Desert Sunlight Expansion", "type": "solar", "mw": 300, "lat": 33.83, "lon": -115.39, "status": "active", "poi": "Red Bluff 500kV", "sub": "Red Bluff"},
            {"name": "Topaz Solar II", "type": "solar", "mw": 250, "lat": 35.0, "lon": -119.95, "status": "active", "poi": "Midway 500kV", "sub": "Midway"},
            {"name": "Rosamond Solar + Storage", "type": "hybrid", "mw": 200, "mw_storage": 100, "lat": 34.87, "lon": -118.17, "status": "active", "poi": "Antelope 230kV", "sub": "Antelope"},
            {"name": "Diablo Winds", "type": "wind", "mw": 150, "lat": 37.87, "lon": -121.62, "status": "active", "poi": "Tesla 230kV", "sub": "Tesla"},
            {"name": "Edwards AFB Solar", "type": "solar", "mw": 500, "lat": 34.92, "lon": -117.88, "status": "active", "poi": "Kramer 500kV", "sub": "Kramer"},
            {"name": "Salton Sea Geothermal Expansion", "type": "geothermal", "mw": 50, "lat": 33.17, "lon": -115.62, "status": "completed", "poi": "Mirage 230kV", "sub": "Mirage"},
            {"name": "Cuyama Valley Storage", "type": "storage", "mw": 400, "mw_storage": 400, "lat": 34.95, "lon": -119.68, "status": "active", "poi": "Midway 230kV", "sub": "Midway"},
            {"name": "Mendota Canal Solar", "type": "solar", "mw": 180, "lat": 36.75, "lon": -120.38, "status": "withdrawn", "poi": "Panoche 230kV", "sub": "Panoche"},
            {"name": "Moss Landing Storage III", "type": "storage", "mw": 300, "mw_storage": 300, "lat": 36.8, "lon": -121.78, "status": "completed", "poi": "Moss Landing 115kV", "sub": "Moss Landing"},
            {"name": "Blythe Mesa Solar", "type": "solar", "mw": 350, "lat": 33.62, "lon": -114.68, "status": "active", "poi": "Colorado River 500kV", "sub": "Colorado River"},
            {"name": "Tehachapi Wind Farm Phase V", "type": "wind", "mw": 200, "lat": 35.13, "lon": -118.45, "status": "active", "poi": "Windhub 500kV", "sub": "Windhub"},
            {"name": "Victorville Solar Park", "type": "solar", "mw": 275, "lat": 34.53, "lon": -117.29, "status": "active", "poi": "Lugo 500kV", "sub": "Lugo"},
            {"name": "San Joaquin Solar I", "type": "solar", "mw": 160, "lat": 37.49, "lon": -121.33, "status": "active", "poi": "Los Banos 230kV", "sub": "Los Banos"},
            {"name": "Palmdale Storage Hub", "type": "storage", "mw": 200, "mw_storage": 200, "lat": 34.58, "lon": -118.12, "status": "active", "poi": "Vincent 230kV", "sub": "Vincent"},
        ],
    },
    "pjm": {
        "state": "VA",
        "projects": [
            {"name": "Fauquier County Solar", "type": "solar", "mw": 200, "lat": 38.72, "lon": -77.81, "status": "active", "poi": "Remington 230kV", "sub": "Remington"},
            {"name": "Northern Virginia Data Center Load", "type": "load", "mw": 500, "lat": 39.04, "lon": -77.49, "status": "active", "poi": "Loudoun 500kV", "sub": "Loudoun"},
            {"name": "Shenandoah Wind", "type": "wind", "mw": 150, "lat": 38.95, "lon": -78.85, "status": "active", "poi": "Valley 138kV", "sub": "Valley"},
            {"name": "Culpeper Solar + Storage", "type": "hybrid", "mw": 180, "mw_storage": 90, "lat": 38.47, "lon": -77.99, "status": "active", "poi": "Culpeper 230kV", "sub": "Culpeper"},
            {"name": "Prince William Storage", "type": "storage", "mw": 250, "mw_storage": 250, "lat": 38.78, "lon": -77.48, "status": "active", "poi": "Gainesville 230kV", "sub": "Gainesville"},
            {"name": "Spotsylvania County Solar II", "type": "solar", "mw": 300, "lat": 38.19, "lon": -77.67, "status": "active", "poi": "Flat Run 230kV", "sub": "Flat Run"},
            {"name": "Stafford County Solar", "type": "solar", "mw": 120, "lat": 38.42, "lon": -77.42, "status": "withdrawn", "poi": "Garrisonville 138kV", "sub": "Garrisonville"},
            {"name": "Rappahannock Solar", "type": "solar", "mw": 225, "lat": 38.68, "lon": -77.78, "status": "active", "poi": "Warrenton 138kV", "sub": "Warrenton"},
        ],
    },
    "miso": {
        "state": "MI",
        "projects": [
            {"name": "Washtenaw Solar Farm", "type": "solar", "mw": 150, "lat": 42.28, "lon": -83.74, "status": "active", "poi": "Milan 138kV", "sub": "Milan"},
            {"name": "Monroe County Wind", "type": "wind", "mw": 200, "lat": 41.92, "lon": -83.55, "status": "active", "poi": "Monroe 345kV", "sub": "Monroe"},
            {"name": "Lenawee Solar Park", "type": "solar", "mw": 250, "lat": 41.89, "lon": -84.06, "status": "active", "poi": "Adrian 138kV", "sub": "Adrian"},
            {"name": "Huron County Wind Farm", "type": "wind", "mw": 300, "lat": 43.88, "lon": -82.88, "status": "active", "poi": "Harbor Beach 138kV", "sub": "Harbor Beach"},
            {"name": "Jackson County Solar + Storage", "type": "hybrid", "mw": 175, "mw_storage": 50, "lat": 42.25, "lon": -84.4, "status": "active", "poi": "Jackson 138kV", "sub": "Jackson"},
            {"name": "Gratiot Wind Energy Center", "type": "wind", "mw": 225, "lat": 43.3, "lon": -84.6, "status": "completed", "poi": "Alma 138kV", "sub": "Alma"},
            {"name": "Thumb Solar Project", "type": "solar", "mw": 100, "lat": 43.48, "lon": -83.04, "status": "active", "poi": "Cass City 138kV", "sub": "Cass City"},
        ],
    },
    "nyiso": {
        "state": "NY",
        "projects": [
            {"name": "Mohawk Valley Solar", "type": "solar", "mw": 120, "lat": 42.98, "lon": -74.99, "status": "active", "poi": "Rotterdam 115kV", "sub": "Rotterdam"},
            {"name": "Finger Lakes Wind", "type": "wind", "mw": 180, "lat": 42.78, "lon": -76.92, "status": "active", "poi": "Homer Hill 115kV", "sub": "Homer Hill"},
            {"name": "Hudson Valley Storage", "type": "storage", "mw": 200, "mw_storage": 200, "lat": 41.7, "lon": -73.93, "status": "active", "poi": "Roseton 345kV", "sub": "Roseton"},
            {"name": "Long Island Offshore Wind", "type": "wind", "mw": 816, "lat": 40.72, "lon": -72.6, "status": "active", "poi": "Holbrook 138kV", "sub": "Holbrook"},
            {"name": "Capital Region Solar", "type": "solar", "mw": 80, "lat": 42.65, "lon": -73.77, "status": "active", "poi": "New Scotland 345kV", "sub": "New Scotland"},
            {"name": "North Country Wind", "type": "wind", "mw": 250, "lat": 44.3, "lon": -75.49, "status": "withdrawn", "poi": "Moses 765kV", "sub": "Moses"},
        ],
    },
    "spp": {
        "state": "OK",
        "projects": [
            {"name": "Canadian County Wind", "type": "wind", "mw": 300, "lat": 35.53, "lon": -97.95, "status": "active", "poi": "Cimarron 345kV", "sub": "Cimarron"},
            {"name": "Panhandle Solar I", "type": "solar", "mw": 200, "lat": 36.45, "lon": -100.2, "status": "active", "poi": "Hitchland 345kV", "sub": "Hitchland"},
            {"name": "Woodward Wind Farm", "type": "wind", "mw": 400, "lat": 36.43, "lon": -99.39, "status": "active", "poi": "Woodward 345kV", "sub": "Woodward"},
            {"name": "Comanche County Solar + Storage", "type": "hybrid", "mw": 250, "mw_storage": 125, "lat": 34.62, "lon": -98.49, "status": "active", "poi": "Lawton 138kV", "sub": "Lawton"},
            {"name": "Grant County Wind", "type": "wind", "mw": 350, "lat": 36.81, "lon": -97.78, "status": "completed", "poi": "Sooner 345kV", "sub": "Sooner"},
            {"name": "Kay County Wind II", "type": "wind", "mw": 275, "lat": 36.85, "lon": -97.14, "status": "active", "poi": "Kaw 345kV", "sub": "Kaw"},
            {"name": "Kingfisher Solar", "type": "solar", "mw": 150, "lat": 35.86, "lon": -97.93, "status": "active", "poi": "Kingfisher 138kV", "sub": "Kingfisher"},
            {"name": "Grady County Storage", "type": "storage", "mw": 200, "mw_storage": 200, "lat": 34.98, "lon": -97.92, "status": "active", "poi": "Newcastle 138kV", "sub": "Newcastle"},
        ],
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Seed interconnection queue")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from sqlalchemy import text, func
    from app.database import SessionLocal
    from app.models.interconnection_queue import InterconnectionQueue
    from app.models.iso import ISO

    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT COUNT(*) FROM interconnection_queue")).scalar()
        if existing > 0:
            logger.info(f"Already {existing} queue entries in DB. Skipping seed.")
            return

        created = []
        for iso_code, data in QUEUE_DATA.items():
            iso = db.query(ISO).filter(
                func.lower(ISO.iso_code) == iso_code.lower()
            ).order_by(ISO.id).first()
            if not iso:
                logger.warning(f"ISO {iso_code} not found, skipping")
                continue

            for i, proj in enumerate(data["projects"]):
                # Generate realistic dates
                entered = date(2023, 1, 1) + timedelta(days=random.randint(0, 730))
                online = entered + timedelta(days=random.randint(365, 1825))
                completed = entered + timedelta(days=random.randint(180, 900)) if proj["status"] == "completed" else None
                withdrawn = entered + timedelta(days=random.randint(90, 540)) if proj["status"] == "withdrawn" else None

                entry = InterconnectionQueue(
                    iso_id=iso.id,
                    queue_id=f"{iso_code.upper()}-{2023 + i // 10:04d}-{(i % 10) + 1:03d}",
                    project_name=proj["name"],
                    state=data["state"],
                    point_of_interconnection=proj.get("poi"),
                    latitude=proj["lat"],
                    longitude=proj["lon"],
                    generation_type=proj["type"],
                    capacity_mw=proj["mw"],
                    capacity_mw_storage=proj.get("mw_storage"),
                    queue_status=proj["status"],
                    date_entered=entered,
                    date_completed=completed,
                    date_withdrawn=withdrawn,
                    proposed_online_date=online,
                    voltage_kv=float(proj["poi"].split()[-1].replace("kV", "")) if "kV" in proj.get("poi", "") else None,
                    substation_name=proj.get("sub"),
                    data_source="seed",
                    source_url=f"https://www.{iso_code}{'energy' if iso_code == 'miso' else ''}.{'com' if iso_code in ('caiso','pjm') else 'org'}/interconnection",
                )
                created.append(entry)

            logger.info(f"  {iso_code}: {len(data['projects'])} projects")

        logger.info(f"\nTotal queue entries: {len(created)}")

        if args.dry_run:
            logger.info("DRY RUN - no changes written")
            return

        db.add_all(created)
        db.commit()
        logger.info(f"Committed {len(created)} interconnection queue entries")

        total = db.execute(text("SELECT COUNT(*) FROM interconnection_queue")).scalar()
        logger.info(f"Total in DB: {total}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
