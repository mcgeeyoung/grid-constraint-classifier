"""Extraction prompt templates for LLM-assisted data structuring.

Each prompt is designed to extract a specific type of structured data
from utility regulatory filings. Prompts instruct the LLM to return
JSON conforming to the expected schema for each extraction type.
"""

SYSTEM_PROMPT = (
    "You are a utility regulatory analyst specializing in electric grid "
    "planning data extraction. Extract structured data from utility filings "
    "with precision. Be exact about numbers and units. If data is ambiguous "
    "or partially visible, note it in the 'notes' field. Only extract what "
    "is explicitly stated in the document. Return valid JSON only."
)

LOAD_FORECAST_PROMPT = """Extract the load forecast data from this utility filing.

Return JSON with this exact structure:
{
    "utility": "<utility name>",
    "forecast_type": "peak_demand|energy|both",
    "base_year": <YYYY>,
    "scenarios": [
        {
            "name": "base|high|low",
            "data": [
                {
                    "year": <YYYY>,
                    "peak_demand_mw": <number or null>,
                    "energy_gwh": <number or null>,
                    "growth_rate_pct": <number or null>
                }
            ]
        }
    ],
    "area_name": "<service territory, zone, or system>",
    "area_type": "system|zone|substation|planning_area",
    "notes": "<any caveats, methodology notes, or data quality issues>"
}

Rules:
- All capacity values in MW, energy in GWh
- growth_rate_pct as percentage (e.g., 2.5 for 2.5%)
- Include all years present in the data
- If only one scenario exists, name it "base"
- If the document contains multiple forecast areas, create separate entries"""

GRID_CONSTRAINT_PROMPT = """Extract grid constraints from this distribution planning document.

Return JSON with this exact structure:
{
    "constraints": [
        {
            "location_name": "<substation, feeder, or circuit name>",
            "location_type": "substation|feeder|circuit|zone|planning_area",
            "constraint_type": "thermal|voltage|capacity|protection|reliability",
            "current_capacity_mw": <number or null>,
            "forecasted_load_mw": <number or null>,
            "headroom_mw": <number or null>,
            "constraint_year": <YYYY or null>,
            "proposed_solution": "<description of proposed mitigation>",
            "proposed_solution_cost_m": <cost in millions of dollars or null>,
            "der_eligible": <true if DER/NWA could address this, false otherwise, null if unknown>,
            "notes": "<additional context>"
        }
    ],
    "utility": "<utility name>",
    "document_context": "<brief description of which section/table this came from>"
}

Rules:
- All capacity/load values in MW
- Cost in millions of dollars
- der_eligible should be true if the document mentions DER, non-wires alternatives, or demand-side solutions
- Include all constraints found, even if some fields are null"""

RESOURCE_NEED_PROMPT = """Extract resource needs from this integrated resource plan or procurement filing.

Return JSON with this exact structure:
{
    "needs": [
        {
            "need_type": "capacity|energy|flexibility|reliability|renewable",
            "need_mw": <number or null>,
            "need_year": <YYYY>,
            "location_type": "system|zone|local|substation",
            "location_name": "<area name or null>",
            "eligible_resource_types": ["solar", "wind", "storage", "DR", "EE", "gas", "nuclear", "other"],
            "procurement_mechanism": "<RFP, bilateral, self-build, etc.>",
            "notes": "<additional context>"
        }
    ],
    "utility": "<utility name>",
    "planning_horizon": "<start year>-<end year>",
    "document_context": "<brief description of source section>"
}

Rules:
- All capacity values in MW
- eligible_resource_types should list ALL types mentioned as eligible
- If no specific location, use location_type "system" and location_name null
- Include year-by-year needs if available"""

HOSTING_CAPACITY_PROMPT = """Extract hosting capacity or integration capacity data from this utility filing.

Return JSON with this exact structure:
{
    "records": [
        {
            "feeder_id": "<feeder or circuit identifier>",
            "substation_name": "<parent substation or null>",
            "hosting_capacity_mw": <number or null>,
            "installed_dg_mw": <number or null>,
            "remaining_capacity_mw": <number or null>,
            "constraining_factor": "<thermal|voltage|protection|other or null>",
            "voltage_kv": <number or null>,
            "notes": "<additional context>"
        }
    ],
    "utility": "<utility name>",
    "data_date": "<date of data if stated>",
    "capacity_unit": "mw|kw",
    "document_context": "<brief description of source>"
}

Rules:
- Normalize all values to the stated unit (MW or kW)
- Include all feeders/circuits found in the document
- constraining_factor should match the primary constraint if multiple exist"""

GENERAL_SUMMARY_PROMPT = """Summarize this utility regulatory filing, focusing on information relevant to grid planning, DER integration, and energy infrastructure.

Return JSON with this exact structure:
{
    "utility": "<utility name>",
    "document_type": "<IRP|DRP|rate_case|testimony|order|report|other>",
    "filing_date": "<date if stated>",
    "key_findings": [
        "<finding 1>",
        "<finding 2>"
    ],
    "quantitative_data": [
        {
            "metric": "<what is being measured>",
            "value": <number>,
            "unit": "<MW|GWh|$M|%|etc>",
            "context": "<brief context>"
        }
    ],
    "der_relevance": "<description of how this relates to DER siting and integration>",
    "data_tables_present": <true|false>,
    "recommended_extraction_types": ["load_forecast", "grid_constraint", "resource_need", "hosting_capacity"],
    "notes": "<any other notable information>"
}

Rules:
- Focus on quantitative data and actionable information
- recommended_extraction_types should list which detailed extraction prompts to run
- Keep key_findings concise (1-2 sentences each)"""


PROMPTS = {
    "load_forecast": LOAD_FORECAST_PROMPT,
    "grid_constraint": GRID_CONSTRAINT_PROMPT,
    "resource_need": RESOURCE_NEED_PROMPT,
    "hosting_capacity": HOSTING_CAPACITY_PROMPT,
    "general_summary": GENERAL_SUMMARY_PROMPT,
}
