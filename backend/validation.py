"""
Clinical Drug Safety Engine — Input/Output Validation

Strict validation pipeline that treats ALL LLM output as untrusted input.
Provides input normalization, fuzzy drug name matching, and output sanitization.

CRITICAL: No raw text from LLM ever reaches the response.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from models import (
    ConfidenceLevel,
    DrugInteraction,
    LLMRawOutput,
    Severity,
)
from safety_rules import KNOWN_DRUGS


# ---------------------------------------------------------------------------
# Fuzzy Matching (Levenshtein Distance)
# ---------------------------------------------------------------------------

def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def fuzzy_match_drug(drug_name: str, max_distance: int = 2) -> Optional[str]:
    """
    Attempt to fuzzy-match a drug name against the known drug dictionary.

    Returns the corrected drug name if a match is found within max_distance,
    or None if no close match exists.
    """
    drug_lower = drug_name.lower().strip()

    # Exact match — no correction needed
    if drug_lower in KNOWN_DRUGS:
        return None  # None means "no correction needed"

    best_match: Optional[str] = None
    best_distance = max_distance + 1

    for known_drug in KNOWN_DRUGS:
        # Quick length check to skip obviously different strings
        if abs(len(drug_lower) - len(known_drug)) > max_distance:
            continue

        distance = _levenshtein_distance(drug_lower, known_drug)
        if distance <= max_distance and distance < best_distance:
            best_distance = distance
            best_match = known_drug

    return best_match


# ---------------------------------------------------------------------------
# Input Normalization
# ---------------------------------------------------------------------------

def normalize_drug_list(drugs: list[str]) -> tuple[list[str], list[str]]:
    """
    Normalize a list of drug names:
    1. Lowercase and strip whitespace
    2. Remove empty strings
    3. Remove duplicates (preserve first occurrence order)
    4. Attempt fuzzy matching for unknown drugs

    Returns:
        tuple of (normalized_drugs, warnings)
    """
    warnings: list[str] = []
    seen: set[str] = set()
    normalized: list[str] = []

    for drug in drugs:
        if not drug or not drug.strip():
            continue

        drug_clean = drug.strip().lower()
        # Remove any non-alphanumeric characters except hyphens, spaces, and periods
        drug_clean = re.sub(r'[^\w\s\-\.]', '', drug_clean).strip()

        if not drug_clean:
            continue

        if drug_clean in seen:
            warnings.append(f"Duplicate drug removed: '{drug_clean}'")
            continue

        # Try fuzzy matching
        correction = fuzzy_match_drug(drug_clean)
        if correction:
            warnings.append(
                f"Possible misspelling corrected: '{drug_clean}' → '{correction}'"
            )
            if correction not in seen:
                seen.add(correction)
                normalized.append(correction)
            else:
                warnings.append(f"Corrected drug '{correction}' already in list, skipping duplicate")
        else:
            seen.add(drug_clean)
            normalized.append(drug_clean)

    return normalized, warnings


def normalize_string_list(items: list[str]) -> list[str]:
    """Normalize a generic string list: lowercase, strip, deduplicate."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or not item.strip():
            continue
        clean = item.strip().lower()
        if clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


# ---------------------------------------------------------------------------
# LLM Output Validation (CRITICAL — treats LLM output as UNTRUSTED)
# ---------------------------------------------------------------------------

def parse_llm_json(raw_output: str) -> Optional[dict]:
    """
    Attempt to parse raw LLM output as JSON.

    Handles common LLM quirks:
    - Leading/trailing whitespace
    - Markdown code fences (```json ... ```)
    - Trailing commas (basic cleanup)

    Returns parsed dict or None if parsing fails.
    """
    if not raw_output or not raw_output.strip():
        return None

    text = raw_output.strip()

    # Remove markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (with optional language tag)
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        # Remove closing fence
        text = re.sub(r'\n?```\s*$', '', text)
        text = text.strip()

    # Remove any text before the first { or after the last }
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace == -1 or last_brace == -1 or first_brace > last_brace:
        return None
    text = text[first_brace:last_brace + 1]

    # Basic trailing comma cleanup (common LLM error)
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*\]', ']', text)

    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            return None
        return result
    except json.JSONDecodeError:
        return None


def validate_llm_output(
    raw_output: str,
    valid_drugs: set[str],
) -> tuple[Optional[list[DrugInteraction]], str]:
    """
    Validate and sanitize LLM output.

    RULES:
    1. Must parse as valid JSON
    2. Must match LLMRawOutput schema
    3. All drug names must be in the valid_drugs set
    4. All severity values must be valid
    5. Hallucinated drug names are STRIPPED
    6. If nothing valid remains, returns None (triggers fallback)

    Args:
        raw_output: Raw string output from LLM
        valid_drugs: Set of drug names that are valid (from input)

    Returns:
        tuple of (validated_interactions or None, rejection_reason)
    """
    # Step 1: Parse JSON
    parsed = parse_llm_json(raw_output)
    if parsed is None:
        return None, "LLM output is not valid JSON"

    # Step 2: Validate against schema
    try:
        llm_output = LLMRawOutput(**parsed)
    except Exception as e:
        return None, f"LLM output does not match expected schema: {e}"

    # Step 3: Validate each interaction
    validated: list[DrugInteraction] = []
    rejected_count = 0
    low_confidence_count = 0

    for interaction in llm_output.interactions:
        # 3a. Check drug names exist in input
        drug_a_lower = interaction.drug_a.lower().strip()
        drug_b_lower = interaction.drug_b.lower().strip()

        if drug_a_lower not in valid_drugs:
            rejected_count += 1
            continue
        if drug_b_lower not in valid_drugs:
            rejected_count += 1
            continue

        # 3b. Check drugs are different
        if drug_a_lower == drug_b_lower:
            rejected_count += 1
            continue

        # 3c. Validate severity
        severity_str = interaction.severity.lower().strip()
        try:
            severity = Severity(severity_str)
            if severity == Severity.CRITICAL:
                # LLM should not assign "critical" — that's for allergies only
                severity = Severity.HIGH
        except ValueError:
            rejected_count += 1
            continue

        # 3d. Validate mechanism (must be non-empty)
        mechanism = interaction.mechanism.strip() if interaction.mechanism else ""
        if not mechanism:
            mechanism = "Drug interaction identified — mechanism details unavailable"

        # 3e. Validate recommendation (must be non-empty)
        recommendation = interaction.clinical_recommendation.strip() if interaction.clinical_recommendation else ""
        if not recommendation:
            recommendation = "Consult physician before co-prescribing these medications"

        # 3f. Validate confidence
        conf_str = interaction.source_confidence.lower().strip() if interaction.source_confidence else "high"
        try:
            confidence = ConfidenceLevel(conf_str)
        except ValueError:
            confidence = ConfidenceLevel.MEDIUM

        if confidence == ConfidenceLevel.LOW:
            low_confidence_count += 1

        validated.append(DrugInteraction(
            drug_a=drug_a_lower,
            drug_b=drug_b_lower,
            severity=severity,
            mechanism=mechanism,
            clinical_recommendation=recommendation,
            source_confidence=confidence,
        ))

    # Step 4: Check if too many interactions were low confidence
    total_interactions = len(validated)
    if total_interactions > 0 and low_confidence_count > total_interactions * 0.5:
        return None, (
            f"LLM output quality too low: {low_confidence_count}/{total_interactions} "
            f"interactions have low confidence"
        )

    # Step 5: Check if too many were rejected (hallucination indicator)
    total_raw = len(llm_output.interactions)
    if total_raw > 0 and rejected_count > total_raw * 0.5:
        return None, (
            f"LLM output likely hallucinated: {rejected_count}/{total_raw} "
            f"interactions contained invalid drug names"
        )

    # Valid output (may be empty list — that's OK, it means no interactions)
    return validated, ""
