# Grid Value Extraction Pipeline: Instruction Guide

This document provides instructions and best practices for building a systematic pipeline to extract grid constraint and loading data from utility planning reports (distribution system plans, integrated resource plans, load forecasts). The extracted data feeds into WattCarbon's grid value metric, which identifies overloaded grid segments and the times of day when constraints occur.

## Project Context

WattCarbon is building a grid value metric for distributed energy resources (DERs). The goal is to programmatically extract data from utility planning PDFs to determine:

- Which grid segments (circuits, substations, feeders) are overloaded or projected to become overloaded
- What times of day and seasons those constraints occur
- The magnitude of the overload (MW or kW)
- The forecast timeline for when constraints emerge

This data enables accurate locational and temporal valuation of DER capacity contributions.

---

## 1. Pipeline Architecture

### Overview

```
PDF Documents
    → Page Rendering (pdf2image / pymupdf)
    → Vision-Based Extraction (LLM with structured output)
    → Validation Layer (programmatic sanity checks)
    → Normalization (units, terminology, geography)
    → Structured Output (JSON / database records)
```

### Design Principles

- **Vision-first extraction.** Always render PDF pages to images and send them to the LLM rather than trying to extract text from the PDF layer. Utility reports frequently have broken table structures, merged cells, scanned pages, and layout complexity that defeats text-based parsing.
- **Two-tier model routing.** Use a cheaper, faster model (Claude Haiku or Gemini Flash) for the initial extraction pass. Route low-confidence results or complex pages to a stronger model (Claude Sonnet or Opus) for re-extraction.
- **Schema-driven extraction.** Define target schemas before writing extraction code. Every LLM call should request output conforming to a specific schema using structured output / tool use.
- **Validate everything.** LLMs will confidently produce incorrect numbers from complex tables. Every extraction must pass programmatic validation before being stored.

---

## 2. Environment Setup

### Dependencies

```bash
# PDF processing
pip install pymupdf pdf2image Pillow

# LLM clients
pip install anthropic openai google-generativeai

# Data processing
pip install pandas pydantic

# Optional: alternative table extraction for hybrid pipeline
pip install pdfplumber camelot-py
```

### Project Structure

```
grid-value-extraction/
├── schemas/              # Pydantic models for extraction targets
│   ├── circuit_loading.py
│   ├── substation_capacity.py
│   ├── load_forecast.py
│   └── common.py         # Shared types (units, time periods, etc.)
├── extraction/
│   ├── renderer.py        # PDF to image conversion
│   ├── extractor.py       # LLM-based extraction logic
│   ├── router.py          # Confidence-based model routing
│   └── prompts/           # Extraction prompt templates
├── validation/
│   ├── checks.py          # Programmatic validation rules
│   └── review.py          # Flagging and review queue logic
├── normalization/
│   ├── units.py           # Unit conversion and standardization
│   ├── terminology.py     # Utility-specific term mapping
│   └── geography.py       # Location normalization
├── output/
│   ├── store.py           # Database or file storage
│   └── export.py          # Export to downstream systems
├── config.py              # Model selection, thresholds, API keys
├── pipeline.py            # Main orchestration
└── tests/
    ├── fixtures/          # Sample PDF pages for testing
    └── test_extraction.py
```

---

## 3. PDF Rendering

### Best Practices

- Render pages at **200-300 DPI**. This balances readability for the LLM against token cost. Start at 200 DPI and increase only if extraction quality is poor on specific documents.
- Use **PNG format** for rendered images. JPEG compression can degrade table lines and small text.
- **Pre-classify pages** before sending to the LLM. Not every page in a 200+ page IRP contains relevant data. Use a fast, cheap classification pass to identify pages that contain tables, maps, or charts related to grid loading. This significantly reduces cost.
- **Crop pages** when possible. If a relevant table occupies only half a page, crop to just the table region. This reduces tokens and improves extraction focus.

### Implementation Notes

```python
import fitz  # pymupdf

def render_pages(pdf_path: str, dpi: int = 200) -> list[tuple[int, bytes]]:
    """Render each page of a PDF to a PNG image."""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Scale factor: 72 DPI is default for PDF
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        pages.append((page_num, pix.tobytes("png")))
    return pages
```

---

## 4. Schema Design

### Core Schemas

Define Pydantic models for each type of data you extract. This ensures consistency and enables structured output from the LLM.

#### Key schemas to define:

**CircuitLoading**: Captures loading data for individual distribution circuits or feeders.
- circuit_id / circuit_name
- substation_name
- utility (e.g., "PG&E", "ConEd")
- peak_load_kw (numeric, always in kW)
- capacity_kw (rated capacity in kW)
- loading_percent (peak_load / capacity)
- peak_period (e.g., "summer_afternoon", "winter_evening")
- peak_months (list of months)
- peak_hours_start, peak_hours_end (24hr format)
- forecast_year
- constraint_status (e.g., "overloaded", "at_risk", "adequate")
- source_document, source_page

**SubstationCapacity**: Captures substation-level data.
- Similar fields to CircuitLoading but at substation granularity
- Number of circuits served
- Planned capital projects (deferrals are the opportunity for DERs)

**LoadForecast**: Captures system or area load growth projections.
- geographic_area
- forecast_year
- projected_peak_mw
- growth_rate_percent
- season (summer / winter)

**PlannedDeferral**: Captures cases where the utility has identified a potential NWA (non-wires alternative) opportunity.
- location
- deferral_value_usd
- required_capacity_kw
- required_duration_hours
- target_year

### Normalization Rules

Encode these in your schemas and normalization layer:

| Field | Rule |
|---|---|
| Capacity / load values | Always store in kW. Convert MW to kW on extraction. |
| Percentages | Store as decimals (0.95 not 95%). |
| Time periods | Use 24hr format. Store as hour integers (e.g., 16 for 4pm). |
| Geographic identifiers | Normalize to a consistent hierarchy: utility > planning_area > substation > circuit. |
| Forecast years | Store as integers. Flag if a document mixes planning horizons. |

---

## 5. Extraction Prompts

### Prompt Design Principles

- **One schema per prompt.** Do not ask the LLM to extract multiple types of data from one page in a single call. It is better to make two focused calls than one overloaded call.
- **Provide the schema explicitly.** Include the Pydantic model or JSON schema in the prompt so the LLM knows exactly what fields to populate.
- **Include examples.** Provide 1-2 examples of correctly extracted records for the schema you are targeting. Use examples from different utilities to show the model how to handle terminology variation.
- **Instruct on uncertainty.** Tell the model to set a field to `null` rather than guessing when data is ambiguous or not present on the page. Include a `confidence` field (0.0-1.0) in every extraction result.
- **Provide document context.** Tell the model which utility published the document, the document type, and the document year. This helps resolve ambiguous references.

### Example Prompt Template

```
You are extracting grid loading data from a utility planning report.

**Document context:**
- Utility: {utility_name}
- Document type: {doc_type} (e.g., "Distribution System Plan", "IRP")
- Publication year: {pub_year}

**Task:** Extract all circuit or feeder loading data from this page into the following schema. Return a JSON array of records.

**Schema:**
{json_schema}

**Rules:**
- Convert all capacity and load values to kW. If the table uses MW, multiply by 1000.
- If peak period or hours are not explicitly stated, set those fields to null.
- Set confidence to a value between 0.0 and 1.0 reflecting how certain you are about each record.
- If the page does not contain relevant loading data, return an empty array.
- Do not infer or calculate values that are not explicitly present in the table.

**Example output:**
{example_output}
```

### Using Structured Output

Prefer Claude's tool use or OpenAI's structured output mode to enforce the schema at the API level rather than relying on the model to produce valid JSON in free text.

```python
# Example using Anthropic tool use for structured extraction
tools = [
    {
        "name": "store_circuit_loading",
        "description": "Store extracted circuit loading records",
        "input_schema": CircuitLoading.model_json_schema()
    }
]
```

---

## 6. Confidence Routing

### Two-Tier Model Strategy

```
Page Image
    → Tier 1 Model (Haiku / Gemini Flash)
        → confidence >= 0.8 → accept result
        → confidence < 0.8 → re-extract with Tier 2 Model (Sonnet / Opus)
            → confidence >= 0.6 → accept with review flag
            → confidence < 0.6 → send to manual review queue
```

### Confidence Signals

Beyond the model's self-reported confidence, flag results for review when:

- Any numeric field is null when it should not be
- Loading percentages exceed 150% (possible unit error)
- Capacity values are outside a reasonable range for the asset type
- The number of extracted records differs significantly from the expected table row count
- The same circuit appears with conflicting values across pages

---

## 7. Validation Layer

### Automated Checks

Implement these programmatic validations on every extraction result:

**Numeric consistency:**
- `loading_percent` should approximately equal `peak_load_kw / capacity_kw`
- If both MW and kW values are present, verify the conversion
- Sum of component loads should not exceed total where a total row is present

**Range checks:**
- Circuit capacity: typically 5,000 - 50,000 kW
- Substation capacity: typically 20,000 - 500,000 kW
- Loading percentage: flag anything above 120% or below 10%
- Forecast years: should be within a reasonable range of the publication year

**Cross-page consistency:**
- The same circuit should not have conflicting capacity values across different tables in the same document
- Substation totals should be consistent with the sum of their constituent circuits

**Temporal consistency:**
- Load forecasts should generally increase over time (unless the document discusses load reduction programs)
- Capacity values should remain stable unless a capital project is planned

### Review Queue

Store flagged records with:
- The original page image
- The raw extraction result
- The specific validation failure
- A link to accept, correct, or reject

Corrections made in review should be logged and can be used to refine extraction prompts over time.

---

## 8. Document Source Catalog

### Priority Data Sources

| Source Type | Granularity | Typical Contents | Key Utilities |
|---|---|---|---|
| Distribution System Plans | Circuit / feeder | Loading data, hosting capacity, planned projects | CA IOUs (PG&E, SCE, SDG&E) |
| Integrated Resource Plans | System / planning area | Capacity needs, resource mix, load forecasts | Most large IOUs |
| Grid Needs Assessments | Circuit / substation | Identified deferral opportunities | CA IOUs (per CPUC requirement) |
| Hosting Capacity Maps | Circuit | Available capacity for new DER interconnection | Varies by state |
| LNBA / Locational Value Studies | Circuit / substation | Dollar value of deferred infrastructure | PG&E (DDOR), ConEd (BQDM) |
| Load Forecasts (FERC/EIA) | Utility / region | System peak and energy projections | All jurisdictional utilities |

### Document Metadata

For each document processed, store:
- Utility name
- Document type
- Publication date
- Regulatory docket number (if applicable)
- URL or file source
- Pages processed
- Extraction date
- Extraction model and version

---

## 9. Cost Management

### Estimation

A typical 200-page utility planning report with ~40 relevant pages at 200 DPI:

- **Page classification pass** (Haiku): ~40 pages * minimal tokens = low cost
- **Extraction pass** (Haiku): ~40 pages * ~1500 input tokens per image + schema/prompt = moderate cost
- **Re-extraction** (Sonnet): ~10-15% of pages = small additional cost

Benchmark your actual costs on a few representative documents before scaling.

### Cost Reduction Strategies

- Classify pages before extraction to skip irrelevant content
- Cache extraction results keyed by document hash + page number
- Use lower DPI where possible (test 150 DPI vs 200 DPI on your documents)
- Batch pages where the same table spans multiple pages (provide consecutive pages in one call with instructions to treat them as a single table)

---

## 10. Testing Strategy

### Fixture-Based Testing

- Collect 5-10 representative pages from different utilities covering each schema type
- Manually annotate the expected extraction output for each fixture
- Run extraction against fixtures and compare to expected output
- Track accuracy metrics: field-level accuracy, record-level completeness, false positive rate

### Regression Testing

- When modifying prompts or changing models, re-run the full fixture suite
- Compare results to the previous version
- Do not deploy prompt changes that reduce accuracy on existing fixtures

### Edge Cases to Cover

- Tables that span multiple pages
- Tables with merged header cells
- Pages with multiple tables (some relevant, some not)
- Scanned documents with lower image quality
- Tables using footnote markers that modify values
- Documents that mix units (MW and kW in the same table)
- Tables where rows represent years and columns represent circuits (transposed from typical layout)

---

## 11. Output Format

### Target Output

The final output for each document should be a structured JSON file or database records conforming to the schemas defined in section 4. Group records by document and include full provenance:

```json
{
  "document": {
    "utility": "PG&E",
    "type": "Distribution System Plan",
    "year": 2024,
    "source_url": "...",
    "processed_at": "2025-01-15T10:30:00Z"
  },
  "circuit_loading": [
    {
      "circuit_name": "Example Circuit 1234",
      "substation_name": "Example Substation",
      "peak_load_kw": 12500,
      "capacity_kw": 14000,
      "loading_percent": 0.893,
      "peak_period": "summer_afternoon",
      "peak_hours_start": 14,
      "peak_hours_end": 18,
      "forecast_year": 2027,
      "constraint_status": "at_risk",
      "confidence": 0.92,
      "source_page": 47
    }
  ],
  "load_forecasts": [],
  "planned_deferrals": []
}
```

---

## 12. Iteration and Improvement

### Prompt Refinement Workflow

1. Run extraction on a new document
2. Manually review a sample of results (especially low-confidence ones)
3. Identify systematic errors (e.g., model consistently misreads a particular table format)
4. Add a targeted example or instruction to the relevant prompt template
5. Re-run on the same document and verify improvement
6. Run regression tests on fixture suite to confirm no degradation

### Expanding Coverage

As you process documents from more utilities, you will encounter new table formats and terminology. Maintain a terminology mapping file that grows over time:

```python
UTILITY_TERM_MAP = {
    "PG&E": {
        "bank capacity": "substation_capacity_kw",
        "feeder normal rating": "circuit_capacity_kw",
    },
    "ConEd": {
        "network load": "peak_load_kw",
        "area station": "substation_name",
    },
}
```

This mapping should be included in extraction prompts for the relevant utility.
