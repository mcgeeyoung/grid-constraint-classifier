"""LLM-assisted extraction using Claude API.

Sends document text (or table text) to Claude with structured extraction
prompts, then parses the JSON response into ExtractedData objects.
"""

import json
import logging
import os
from typing import Optional

from .base import Confidence, ExtractedData, ExtractionType
from .extraction_prompts import PROMPTS, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Default model for extraction
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
MAX_INPUT_CHARS = 100_000  # ~25K tokens


def extract_with_llm(
    text: str,
    extraction_type: str,
    utility_name: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
) -> Optional[ExtractedData]:
    """Use Claude to extract structured data from document text.

    Args:
        text: Document text or table text to extract from.
        extraction_type: One of the keys in PROMPTS dict.
        utility_name: Utility name for context.
        model: Claude model to use.
        max_tokens: Max response tokens.

    Returns:
        ExtractedData object or None if extraction fails.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None

    prompt_template = PROMPTS.get(extraction_type)
    if not prompt_template:
        logger.error(f"Unknown extraction type: {extraction_type}")
        return None

    model = model or DEFAULT_MODEL

    # Truncate text if too long
    if len(text) > MAX_INPUT_CHARS:
        logger.warning(
            f"Text truncated from {len(text)} to {MAX_INPUT_CHARS} chars"
        )
        text = text[:MAX_INPUT_CHARS]

    # Build user message
    user_content = f"Utility: {utility_name}\n\n" if utility_name else ""
    user_content += f"Document text:\n\n{text}\n\n{prompt_template}"

    logger.info(
        f"LLM extraction: type={extraction_type}, model={model}, "
        f"input_chars={len(text)}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )

        response_text = response.content[0].text.strip()

        # Parse JSON from response (handle markdown code blocks)
        json_text = _extract_json(response_text)
        data = json.loads(json_text)

        # Determine confidence based on response characteristics
        confidence = _assess_confidence(data, extraction_type)

        # Map string to enum
        etype_map = {
            "load_forecast": ExtractionType.LOAD_FORECAST,
            "grid_constraint": ExtractionType.GRID_CONSTRAINT,
            "resource_need": ExtractionType.RESOURCE_NEED,
            "hosting_capacity": ExtractionType.HOSTING_CAPACITY,
            "general_summary": ExtractionType.GENERAL_SUMMARY,
        }

        return ExtractedData(
            extraction_type=etype_map.get(extraction_type, ExtractionType.GENERAL_SUMMARY),
            data=data,
            confidence=confidence,
            raw_text_snippet=text[:500],
            llm_model=model,
            notes=f"Extracted via {model}",
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.debug(f"Raw response: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None


def extract_table_with_llm(
    table_text: str,
    extraction_type: str,
    utility_name: Optional[str] = None,
    table_context: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[ExtractedData]:
    """Extract structured data from a table rendered as text.

    Wraps extract_with_llm with additional table context.
    """
    context = ""
    if table_context:
        context = f"Table context: {table_context}\n\n"

    full_text = f"{context}Table data:\n{table_text}"
    return extract_with_llm(full_text, extraction_type, utility_name, model)


def _extract_json(text: str) -> str:
    """Extract JSON from a response that may contain markdown code blocks."""
    # Try to find JSON in code blocks
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()

    # Try to find raw JSON (starts with { or [)
    for i, c in enumerate(text):
        if c in ("{", "["):
            # Find matching closing bracket
            depth = 0
            for j in range(i, len(text)):
                if text[j] in ("{", "["):
                    depth += 1
                elif text[j] in ("}", "]"):
                    depth -= 1
                    if depth == 0:
                        return text[i:j + 1]
            break

    return text


def _assess_confidence(data: dict, extraction_type: str) -> Confidence:
    """Assess confidence of an LLM extraction based on data completeness."""
    if extraction_type == "load_forecast":
        scenarios = data.get("scenarios", [])
        if scenarios and all(
            len(s.get("data", [])) > 0 for s in scenarios
        ):
            # Check if numeric values are present
            has_numbers = any(
                d.get("peak_demand_mw") is not None or d.get("energy_gwh") is not None
                for s in scenarios
                for d in s.get("data", [])
            )
            return Confidence.HIGH if has_numbers else Confidence.MEDIUM
        return Confidence.LOW

    elif extraction_type == "grid_constraint":
        constraints = data.get("constraints", [])
        if constraints and all(
            c.get("location_name") and c.get("constraint_type")
            for c in constraints
        ):
            return Confidence.HIGH if len(constraints) > 1 else Confidence.MEDIUM
        return Confidence.LOW

    elif extraction_type == "resource_need":
        needs = data.get("needs", [])
        if needs and all(n.get("need_type") for n in needs):
            return Confidence.MEDIUM
        return Confidence.LOW

    elif extraction_type == "hosting_capacity":
        records = data.get("records", [])
        if records and all(r.get("feeder_id") for r in records):
            return Confidence.HIGH if len(records) > 3 else Confidence.MEDIUM
        return Confidence.LOW

    return Confidence.MEDIUM
