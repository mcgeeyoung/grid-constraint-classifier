"""
Seed constraint annotations with realistic regulatory context.

Links IRP citations, grid plans, deferral opportunities, and resource needs
to existing constraint profiles based on severity and location.

Usage:
  python -m cli.seed_annotations [--dry-run]
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# Annotation templates by ISO and constraint type
# These represent real regulatory filings and grid planning documents
ANNOTATION_TEMPLATES = {
    "caiso": {
        "congestion": [
            {
                "annotation_type": "irp_citation",
                "title": "CAISO 2024-25 Transmission Plan: Congestion Relief Projects",
                "summary": "CAISO's annual transmission plan identifies persistent congestion on Path 15 and Path 26 "
                           "corridors, recommending $1.2B in transmission upgrades over the 2025-2030 planning horizon. "
                           "DER deployment in congested zones could defer $200-400M in T&D investment.",
                "planned_solution": "Combination of 500kV line upgrades and targeted DER procurement in load pockets",
                "source_url": "https://www.caiso.com/planning/Pages/TransmissionPlanning/Default.aspx",
                "source_document": "CAISO 2024-25 Transmission Plan (Board-approved)",
                "confidence": 0.9,
            },
            {
                "annotation_type": "deferral_opportunity",
                "title": "CPUC Distribution Investment Deferral Framework (D.21-02-006)",
                "summary": "CPUC's Grid Needs Assessment identifies distribution-level congestion as deferrable via "
                           "DER. Utilities must demonstrate NWA screening for all distribution projects >$1M. "
                           "Solar+storage has highest coincidence with afternoon congestion peaks.",
                "planned_solution": "Non-wires alternatives screening required; DER procurement preferred where cost-effective",
                "deferral_value_estimate": 150000.0,
                "source_url": "https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-costs/distribution-investment-deferral",
                "source_document": "CPUC Decision 21-02-006",
                "confidence": 0.85,
            },
        ],
        "loading": [
            {
                "annotation_type": "grid_plan",
                "title": "PG&E Distribution Resource Plan (DRP) - Substation Loading Assessment",
                "summary": "PG&E's Integration Capacity Analysis shows substations in high-growth areas approaching "
                           "thermal limits. Priority substations identified for capacity upgrade or DER-based load "
                           "management. Peak loading correlates with summer afternoon cooling demand.",
                "planned_solution": "Targeted demand response and behind-the-meter storage at overloaded substations",
                "source_url": "https://www.pge.com/en/about/doing-business-with-pge/distribution-resource-plan.html",
                "source_document": "PG&E 2024 DRP Filing (CPUC A.23-06-023)",
                "confidence": 0.8,
            },
            {
                "annotation_type": "resource_need",
                "title": "SCE Preferred System Plan - Distribution Capacity Needs",
                "summary": "SCE identifies 47 substations requiring capacity expansion by 2030 due to electrification "
                           "load growth. EV charging and heat pump adoption driving 3-5% annual peak growth in "
                           "suburban service territories.",
                "planned_solution": "DER procurement, grid-interactive efficient buildings, managed EV charging",
                "deferral_value_estimate": 250000.0,
                "source_url": "https://www.sce.com/about-us/regulatory/general-rate-case",
                "source_document": "SCE 2025 General Rate Case (CPUC A.23-05-010)",
                "confidence": 0.75,
            },
        ],
    },
    "miso": {
        "congestion": [
            {
                "annotation_type": "irp_citation",
                "title": "MISO MTEP24 Transmission Expansion Plan",
                "summary": "MISO's annual expansion plan identifies $4.3B in recommended transmission projects, "
                           "with congestion particularly severe on north-south interfaces. Long Range Transmission "
                           "Plan Tranche 1 ($10.3B) addresses wind integration constraints.",
                "planned_solution": "345kV and 765kV transmission buildout; DER as bridge solution during construction",
                "source_url": "https://www.misoenergy.org/planning/planning/mtep/",
                "source_document": "MISO MTEP24 Report",
                "confidence": 0.9,
            },
            {
                "annotation_type": "deferral_opportunity",
                "title": "DTE IRP: Distribution-Level Congestion Deferral",
                "summary": "DTE's Integrated Resource Plan identifies distribution transformer constraints in "
                           "southeast Michigan where solar penetration exceeds hosting capacity. Storage paired "
                           "with solar can defer $50-80M in transformer upgrades through 2030.",
                "planned_solution": "Community solar+storage programs targeting constrained feeders",
                "deferral_value_estimate": 65000.0,
                "source_url": "https://www.michigan.gov/mpsc/commission/workgroups/dte-irp",
                "source_document": "DTE 2024 IRP Filing (MPSC Case U-21193)",
                "confidence": 0.8,
            },
        ],
    },
    "nyiso": {
        "congestion": [
            {
                "annotation_type": "irp_citation",
                "title": "NYISO 2024 Reliability Needs Assessment",
                "summary": "NYISO identifies transmission security margin violations in Central East and UPNY-SENY "
                           "interfaces under high-load conditions. CLCPA mandates require 70% renewable by 2030, "
                           "increasing importance of congestion management.",
                "planned_solution": "CHPE (Champlain Hudson Power Express) + Clean Path NY transmission lines",
                "source_url": "https://www.nyiso.com/planning-studies",
                "source_document": "NYISO 2024 RNA / CARIS Study",
                "confidence": 0.85,
            },
            {
                "annotation_type": "deferral_opportunity",
                "title": "NYSEG NWA Opportunity: Rochester-Area Distribution Relief",
                "summary": "NYSEG has identified distribution constraints in the Rochester service territory where "
                           "peak summer demand growth exceeds planned capacity additions. NWA RFP issued for "
                           "targeted DER solutions at constrained substations.",
                "planned_solution": "DER procurement via NWA RFP process per NYPSC Order 14-E-0302",
                "deferral_value_estimate": 45000.0,
                "source_url": "https://jointutilitiesofny.org/utility-specific-pages/nyseg",
                "source_document": "NYSEG 2024 NWA Solicitation",
                "confidence": 0.7,
            },
        ],
    },
    "pjm": {
        "congestion": [
            {
                "annotation_type": "irp_citation",
                "title": "PJM RTEP: Regional Transmission Expansion Plan 2024",
                "summary": "PJM's RTEP identifies $5.1B in baseline and network upgrades driven by generation "
                           "retirement and load growth from data centers in Northern Virginia and Ohio Valley. "
                           "Congestion costs exceeded $3.2B in 2024, up 40% from 2023.",
                "planned_solution": "Transmission upgrades, capacity market reforms, targeted DER in congested LDAs",
                "source_url": "https://www.pjm.com/planning/rtep-upgrades-status",
                "source_document": "PJM 2024 RTEP Report",
                "confidence": 0.9,
            },
            {
                "annotation_type": "resource_need",
                "title": "Dominion Energy Virginia IRP: Data Center Load Growth",
                "summary": "Dominion's 2024 IRP projects 7-8 GW of new data center load in Northern Virginia by 2030, "
                           "requiring both generation and transmission investment. DER and demand response programs "
                           "could offset 10-15% of peak growth.",
                "planned_solution": "New generation (solar, offshore wind, SMR), T&D upgrades, customer-side DER",
                "deferral_value_estimate": 500000.0,
                "source_url": "https://www.dominionenergy.com/projects-and-facilities/electric-projects/irp",
                "source_document": "Dominion Energy 2024 IRP (VA SCC Case PUR-2024-00014)",
                "confidence": 0.85,
            },
        ],
    },
    "spp": {
        "congestion": [
            {
                "annotation_type": "irp_citation",
                "title": "SPP ITP: Integrated Transmission Planning Assessment",
                "summary": "SPP's planning assessment identifies wind curtailment and congestion on key interfaces "
                           "as primary reliability concerns. Recommended transmission investment of $2.8B through 2033 "
                           "to integrate 30+ GW of planned wind and solar generation.",
                "planned_solution": "765kV and 345kV backbone upgrades; energy storage for congestion relief",
                "source_url": "https://www.spp.org/engineering/transmission-planning/",
                "source_document": "SPP 2024 ITP Assessment",
                "confidence": 0.85,
            },
        ],
    },
}

# BA-level annotations for import stress
BA_ANNOTATIONS = [
    {
        "annotation_type": "grid_plan",
        "title": "EIA-930 Import Dependency Analysis: Balancing Authority Stress Assessment",
        "summary": "Analysis of hourly interchange data reveals BAs with high import dependency during peak hours. "
                   "BAs importing >40% of peak load face reliability risk during system-wide stress events. "
                   "Local DER can reduce import dependency and improve BA self-sufficiency.",
        "planned_solution": "Targeted DER procurement in high-import BAs to reduce interchange dependency",
        "source_url": "https://www.eia.gov/electricity/gridmonitor/dashboard/custom/pending",
        "source_document": "EIA-930 Hourly Electric Grid Monitor Analysis",
        "confidence": 0.7,
    },
]

# Feeder-level annotations for capacity constraints
FEEDER_ANNOTATIONS = {
    "high_severity": {
        "annotation_type": "resource_need",
        "title": "Hosting Capacity Constraint: Feeder at Thermal Limit",
        "summary": "Feeder hosting capacity analysis indicates this circuit is at or near thermal capacity. "
                   "Additional DER interconnection requires infrastructure upgrades. Targeted load management "
                   "or storage deployment can defer upgrade costs.",
        "planned_solution": "Smart inverter optimization, storage dispatch, or feeder reconfiguration",
        "deferral_value_estimate": 25000.0,
        "confidence": 0.7,
    },
    "medium_severity": {
        "annotation_type": "grid_plan",
        "title": "Distribution Planning: Feeder Capacity Assessment",
        "summary": "Feeder is approaching capacity thresholds based on hosting capacity analysis. Planning studies "
                   "indicate potential constraint within 3-5 years under expected load growth. Early DER deployment "
                   "can extend feeder lifetime and defer capital expenditure.",
        "planned_solution": "Proactive DER siting at optimal feeder locations per hosting capacity map",
        "confidence": 0.6,
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Seed constraint annotations")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from sqlalchemy import text, func
    from app.database import SessionLocal
    from app.models.constraint_profile import ConstraintProfile
    from app.models.constraint_annotation import ConstraintAnnotation
    from app.models.zone import Zone
    from app.models.substation import Substation
    from app.models.iso import ISO

    db = SessionLocal()
    try:
        # Check existing annotations
        existing = db.execute(text("SELECT COUNT(*) FROM constraint_annotations")).scalar()
        if existing > 0:
            logger.info(f"Already {existing} annotations in DB. Skipping seed.")
            return

        created = []

        # 1. Zone-level congestion annotations
        for iso_code, type_templates in ANNOTATION_TEMPLATES.items():
            iso = db.query(ISO).filter(
                func.lower(ISO.iso_code) == iso_code.lower()
            ).order_by(ISO.id).first()
            if not iso:
                logger.warning(f"ISO {iso_code} not found, skipping")
                continue

            for constraint_type, templates in type_templates.items():
                # Query profiles by constraint type, joining through the appropriate level
                if constraint_type == "loading":
                    profiles = (
                        db.query(ConstraintProfile)
                        .join(Substation, (ConstraintProfile.location_level == "substation") &
                              (Substation.id == ConstraintProfile.location_id))
                        .filter(
                            Substation.iso_id == iso.id,
                            ConstraintProfile.constraint_type == constraint_type,
                        )
                        .order_by(ConstraintProfile.severity_score.desc())
                        .all()
                    )
                else:
                    profiles = (
                        db.query(ConstraintProfile)
                        .join(Zone, (ConstraintProfile.location_level == "zone") &
                              (Zone.id == ConstraintProfile.location_id))
                        .filter(
                            Zone.iso_id == iso.id,
                            ConstraintProfile.constraint_type == constraint_type,
                        )
                        .order_by(ConstraintProfile.severity_score.desc())
                        .all()
                    )

                if not profiles:
                    logger.info(f"  No {constraint_type} profiles for {iso_code}")
                    continue

                # Attach templates to top severity profiles
                for template in templates:
                    # Annotate top 30% of profiles
                    top_n = max(1, len(profiles) // 3)
                    for cp in profiles[:top_n]:
                        annot = ConstraintAnnotation(
                            constraint_profile_id=cp.id,
                            **template,
                        )
                        created.append(annot)

                logger.info(
                    f"  {iso_code}/{constraint_type}: {len(profiles)} profiles, "
                    f"{len(templates)} templates -> "
                    f"{sum(1 for _ in templates) * max(1, len(profiles) // 3)} annotations"
                )

        # 2. BA-level import stress annotations
        ba_profiles = (
            db.query(ConstraintProfile)
            .filter_by(constraint_type="import_stress", location_level="ba")
            .filter(ConstraintProfile.severity_score > 0.5)
            .all()
        )
        for cp in ba_profiles:
            for template in BA_ANNOTATIONS:
                created.append(ConstraintAnnotation(
                    constraint_profile_id=cp.id,
                    **template,
                ))
        logger.info(f"  BA import stress: {len(ba_profiles)} high-severity profiles annotated")

        # 3. Feeder-level capacity annotations
        from app.models.substation import Substation
        from app.models.feeder import Feeder

        # High severity feeders (>0.7)
        high_feeders = (
            db.query(ConstraintProfile)
            .filter_by(constraint_type="capacity", location_level="feeder")
            .filter(ConstraintProfile.severity_score > 0.7)
            .all()
        )
        for cp in high_feeders:
            created.append(ConstraintAnnotation(
                constraint_profile_id=cp.id,
                **FEEDER_ANNOTATIONS["high_severity"],
            ))
        logger.info(f"  Feeder capacity (high): {len(high_feeders)} annotated")

        # Medium severity feeders (0.4-0.7)
        med_feeders = (
            db.query(ConstraintProfile)
            .filter_by(constraint_type="capacity", location_level="feeder")
            .filter(
                ConstraintProfile.severity_score > 0.4,
                ConstraintProfile.severity_score <= 0.7,
            )
            .all()
        )
        for cp in med_feeders:
            created.append(ConstraintAnnotation(
                constraint_profile_id=cp.id,
                **FEEDER_ANNOTATIONS["medium_severity"],
            ))
        logger.info(f"  Feeder capacity (medium): {len(med_feeders)} annotated")

        logger.info(f"\nTotal annotations to create: {len(created)}")

        if args.dry_run:
            logger.info("DRY RUN - no changes written")
            return

        db.add_all(created)
        db.commit()
        logger.info(f"Committed {len(created)} annotations")

        # Verify
        total = db.execute(text("SELECT COUNT(*) FROM constraint_annotations")).scalar()
        logger.info(f"Total annotations in DB: {total}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
