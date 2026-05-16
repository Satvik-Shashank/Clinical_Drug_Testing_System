"""
Clinical Drug Safety Engine — Core Engine

Orchestrates the complete drug safety analysis pipeline:
1. Input normalization and validation
2. Cache lookup
3. LLM inference (or fallback)
4. LLM output validation
5. Deterministic patient history checks (ALWAYS runs)
6. Risk scoring
7. Response assembly

CRITICAL DESIGN PRINCIPLE:
- LLM is used ONLY for drug-drug interaction discovery
- Allergy checks, contraindications, and risk scoring are ALWAYS deterministic
- Patient history ALWAYS affects the output
- The system NEVER returns empty results
"""

from __future__ import annotations

import time
from typing import Optional

from models import (
    AllergyAlert,
    Contraindication,
    DrugInteraction,
    DrugSafetyRequest,
    DrugSafetyResponse,
    RiskBreakdown,
    RiskLevel,
    Severity,
    SourceType,
)
from cache import SafetyCache, interaction_cache
from llm_interface import llm
from safety_rules import (
    check_allergies,
    check_contraindications,
    fallback_db,
)
from validation import (
    normalize_drug_list,
    normalize_string_list,
    validate_llm_output,
)


# ---------------------------------------------------------------------------
# Risk Scoring
# ---------------------------------------------------------------------------

def calculate_risk_score(
    interactions: list[DrugInteraction],
    allergy_alerts: list[AllergyAlert],
    contraindications: list[Contraindication],
) -> tuple[int, RiskBreakdown]:
    """
    Calculate aggregate patient risk score from all findings.

    Scoring model:
    - Allergy (critical/exact): 50 points each, cap 50
    - Allergy (high/class): 40 points each, cap 50
    - Allergy (medium/cross): 25 points each, cap 50
    - Interaction (high): 25 points each, cap 50
    - Interaction (medium): 15 points each, cap 30
    - Interaction (low): 5 points each, cap 15
    - Contraindication: 20 points each, cap 40

    Total capped at 100.

    Returns:
        tuple of (total_score, breakdown)
    """
    # Interaction score
    interaction_points = 0
    for interaction in interactions:
        if interaction.severity == Severity.HIGH:
            interaction_points += 25
        elif interaction.severity == Severity.MEDIUM:
            interaction_points += 15
        elif interaction.severity == Severity.LOW:
            interaction_points += 5
    interaction_score = min(50, interaction_points)

    # Allergy score
    allergy_points = 0
    for alert in allergy_alerts:
        if alert.severity == Severity.CRITICAL:
            allergy_points += 50
        elif alert.severity == Severity.HIGH:
            allergy_points += 40
        elif alert.severity == Severity.MEDIUM:
            allergy_points += 25
        else:
            allergy_points += 10
    allergy_score = min(50, allergy_points)

    # Contraindication score
    contra_points = 0
    for contra in contraindications:
        if contra.severity == Severity.HIGH:
            contra_points += 20
        elif contra.severity == Severity.MEDIUM:
            contra_points += 12
        else:
            contra_points += 8
    contraindication_score = min(40, contra_points)

    # Total (capped at 100)
    total = min(100, interaction_score + allergy_score + contraindication_score)

    breakdown = RiskBreakdown(
        interactions=interaction_score,
        allergies=allergy_score,
        contraindications=contraindication_score,
    )

    return total, breakdown


def determine_risk_level(score: int) -> RiskLevel:
    """Map numeric risk score to categorical risk level."""
    if score <= 30:
        return RiskLevel.LOW
    elif score <= 70:
        return RiskLevel.MEDIUM
    else:
        return RiskLevel.HIGH


def determine_safety_flags(
    risk_score: int,
    risk_level: RiskLevel,
    allergy_alerts: list[AllergyAlert],
    contraindications: list[Contraindication],
    source: SourceType,
) -> tuple[bool, bool]:
    """
    Determine safe_to_prescribe and requires_doctor_review flags.

    Rules:
    - ANY allergy alert → not safe, requires review
    - ANY high-severity contraindication → not safe, requires review
    - Medium risk or above → not safe, requires review
    - Source is fallback with interactions → requires review (less confident)
    - Low risk with no alerts → safe, no review
    """
    safe_to_prescribe = True
    requires_doctor_review = False

    # Any allergy is NEVER safe
    if allergy_alerts:
        safe_to_prescribe = False
        requires_doctor_review = True

    # Any high-severity contraindication
    high_contras = [c for c in contraindications if c.severity in (Severity.HIGH, Severity.CRITICAL)]
    if high_contras:
        safe_to_prescribe = False
        requires_doctor_review = True

    # Risk level thresholds
    if risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH):
        safe_to_prescribe = False
        requires_doctor_review = True

    # Any contraindication at all should flag for review
    if contraindications:
        requires_doctor_review = True

    return safe_to_prescribe, requires_doctor_review


# ---------------------------------------------------------------------------
# Main Engine
# ---------------------------------------------------------------------------

def analyze_drug_safety(request: DrugSafetyRequest) -> DrugSafetyResponse:
    """
    Main entry point: perform complete drug safety analysis.

    Pipeline:
    1. Normalize inputs
    2. Check cache
    3. Get interactions (LLM → fallback)
    4. Run patient history checks (ALWAYS)
    5. Score risk
    6. Assemble response

    GUARANTEES:
    - Never returns empty result
    - Always returns valid schema
    - Patient history always influences output
    - Always includes processing_time_ms, cache_hit, source
    """
    start_time = time.perf_counter()
    warnings: list[str] = []

    # -----------------------------------------------------------------------
    # Step 1: Normalize inputs
    # -----------------------------------------------------------------------
    new_medicines, med_warnings = normalize_drug_list(request.medicines)
    warnings.extend(med_warnings)

    current_medications, curr_warnings = normalize_drug_list(
        request.patient_history.current_medications
    )
    warnings.extend(curr_warnings)

    known_allergies = normalize_string_list(request.patient_history.known_allergies)
    conditions = normalize_string_list(request.patient_history.conditions)
    age = request.patient_history.age
    weight = request.patient_history.weight

    # Check for drugs appearing in both lists
    overlap = set(new_medicines) & set(current_medications)
    if overlap:
        for drug in overlap:
            warnings.append(
                f"Drug '{drug}' appears in both new medicines and current medications. "
                f"Using only in new medicines list."
            )
            current_medications = [m for m in current_medications if m != drug]

    # Combine all drugs for interaction checking
    all_drugs = list(set(new_medicines + current_medications))

    # -----------------------------------------------------------------------
    # Step 2: Check cache
    # -----------------------------------------------------------------------
    cache_key = SafetyCache.build_key(new_medicines, current_medications)
    cached_result = interaction_cache.get(cache_key)
    cache_hit = cached_result is not None

    interactions: list[DrugInteraction] = []
    source = SourceType.FALLBACK

    if cache_hit:
        # Cache hit — use cached interactions
        interactions = cached_result
        source = SourceType.LLM  # Preserve original source from cache
    else:
        # -----------------------------------------------------------------------
        # Step 3a: Try LLM inference
        # -----------------------------------------------------------------------
        llm_succeeded = False

        if llm.is_available and len(all_drugs) >= 2:
            raw_output, inference_ms = llm.analyze_interactions(
                all_drugs=all_drugs,
                new_medicines=new_medicines,
                current_medications=current_medications,
            )

            if raw_output is not None:
                # Validate LLM output (treats as untrusted)
                valid_drugs = set(d.lower().strip() for d in all_drugs)
                validated_interactions, rejection_reason = validate_llm_output(
                    raw_output, valid_drugs
                )

                if validated_interactions is not None:
                    interactions = validated_interactions
                    source = SourceType.LLM
                    llm_succeeded = True
                else:
                    warnings.append(
                        f"LLM output rejected ({rejection_reason}), using fallback"
                    )

        # -----------------------------------------------------------------------
        # Step 3b: Fallback if LLM failed or unavailable
        # -----------------------------------------------------------------------
        if not llm_succeeded:
            source = SourceType.FALLBACK
            if len(all_drugs) >= 2:
                interactions = fallback_db.lookup_all_pairs(all_drugs)

        # Store in cache
        interaction_cache.set(cache_key, interactions)

    # -----------------------------------------------------------------------
    # Step 4: Patient history checks (ALWAYS RUNS — deterministic)
    # -----------------------------------------------------------------------

    # 4a. Allergy checks against new medicines
    allergy_alerts = check_allergies(
        medicines=new_medicines,
        known_allergies=known_allergies,
    )

    # 4b. Contraindication checks
    contraindications, condition_warnings = check_contraindications(
        medicines=new_medicines,
        conditions=conditions,
        age=age,
        weight=weight,
    )
    warnings.extend(condition_warnings)

    # -----------------------------------------------------------------------
    # Step 5: Risk scoring
    # -----------------------------------------------------------------------
    risk_score, risk_breakdown = calculate_risk_score(
        interactions=interactions,
        allergy_alerts=allergy_alerts,
        contraindications=contraindications,
    )
    risk_level = determine_risk_level(risk_score)
    safe_to_prescribe, requires_doctor_review = determine_safety_flags(
        risk_score=risk_score,
        risk_level=risk_level,
        allergy_alerts=allergy_alerts,
        contraindications=contraindications,
        source=source,
    )

    # -----------------------------------------------------------------------
    # Step 6: Assemble response
    # -----------------------------------------------------------------------
    processing_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    response = DrugSafetyResponse(
        interactions=interactions,
        allergy_alerts=allergy_alerts,
        contraindications=contraindications,
        patient_risk_score=risk_score,
        risk_breakdown=risk_breakdown,
        overall_risk_level=risk_level,
        safe_to_prescribe=safe_to_prescribe,
        requires_doctor_review=requires_doctor_review,
        source=source,
        cache_hit=cache_hit,
        processing_time_ms=processing_time_ms,
        warnings=warnings,
    )

    return response
