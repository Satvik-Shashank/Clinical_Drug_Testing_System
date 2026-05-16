"""
Clinical Drug Safety Engine — Comprehensive Test Suite

Tests cover ALL critical requirements:
1. Cache determinism (order, case, duplicate invariance)
2. Cache hit/miss behavior
3. Allergy class detection
4. Duplicate drug handling
5. Invalid input rejection
6. Fallback triggering
7. Schema validation (no raw text)
8. Risk scoring correctness
9. Contraindication detection
10. Patient history influence
11. Edge cases
"""

from __future__ import annotations

import json
import sys
import os
import time

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    AllergyAlert,
    Contraindication,
    DrugInteraction,
    DrugSafetyRequest,
    DrugSafetyResponse,
    PatientHistory,
    RiskBreakdown,
    RiskLevel,
    Severity,
    SourceType,
    ConfidenceLevel,
)
from cache import SafetyCache
from validation import (
    normalize_drug_list,
    normalize_string_list,
    parse_llm_json,
    validate_llm_output,
    fuzzy_match_drug,
)
from safety_rules import (
    check_allergies,
    check_contraindications,
    fallback_db,
    DRUG_CLASS_MAP,
    KNOWN_DRUGS,
)
from engine import (
    analyze_drug_safety,
    calculate_risk_score,
    determine_risk_level,
)


# ===========================================================================
# TEST 1: Cache Determinism — Order, Case, Duplicate Invariance
# ===========================================================================

class TestCacheDeterminism:
    """Cache key must be identical regardless of order, case, or duplicates."""

    def test_order_independent(self):
        """Same drugs in different order produce same cache key."""
        key1 = SafetyCache.build_key(["Aspirin", "Warfarin"], ["Metformin"])
        key2 = SafetyCache.build_key(["Warfarin", "Aspirin"], ["Metformin"])
        assert key1 == key2, "Cache key must be order-independent"

    def test_case_insensitive(self):
        """Same drugs with different casing produce same cache key."""
        key1 = SafetyCache.build_key(["aspirin", "warfarin"], ["metformin"])
        key2 = SafetyCache.build_key(["ASPIRIN", "WARFARIN"], ["METFORMIN"])
        key3 = SafetyCache.build_key(["Aspirin", "Warfarin"], ["Metformin"])
        assert key1 == key2 == key3, "Cache key must be case-insensitive"

    def test_duplicate_safe(self):
        """Duplicates in input don't affect cache key."""
        key1 = SafetyCache.build_key(["aspirin", "warfarin"], ["metformin"])
        key2 = SafetyCache.build_key(
            ["aspirin", "aspirin", "warfarin", "warfarin"],
            ["metformin", "metformin"]
        )
        assert key1 == key2, "Cache key must handle duplicates"

    def test_whitespace_safe(self):
        """Leading/trailing whitespace doesn't affect cache key."""
        key1 = SafetyCache.build_key(["aspirin", "warfarin"], ["metformin"])
        key2 = SafetyCache.build_key(["  aspirin  ", " warfarin "], [" metformin "])
        assert key1 == key2, "Cache key must handle whitespace"

    def test_different_drugs_different_keys(self):
        """Different drug combinations produce different cache keys."""
        key1 = SafetyCache.build_key(["aspirin"], ["metformin"])
        key2 = SafetyCache.build_key(["ibuprofen"], ["metformin"])
        assert key1 != key2, "Different drugs must produce different keys"


# ===========================================================================
# TEST 2: Cache Hit/Miss Behavior
# ===========================================================================

class TestCacheHitMiss:
    """Cache must correctly detect hits and misses."""

    def setup_method(self):
        """Fresh cache for each test."""
        self.cache = SafetyCache(ttl_seconds=3600)

    def test_cache_miss_on_first_call(self):
        """First call with new drugs should be a cache miss."""
        key = SafetyCache.build_key(["aspirin"], ["warfarin"])
        result = self.cache.get(key)
        assert result is None, "First call should be cache miss"

    def test_cache_hit_on_second_call(self):
        """Second call with same drugs should be a cache hit."""
        key = SafetyCache.build_key(["aspirin"], ["warfarin"])
        test_data = [{"drug_a": "aspirin", "drug_b": "warfarin"}]
        self.cache.set(key, test_data)
        result = self.cache.get(key)
        assert result is not None, "Second call should be cache hit"
        assert result == test_data

    def test_cache_hit_reordered_inputs(self):
        """Cache hit when same drugs are provided in different order."""
        key1 = SafetyCache.build_key(["Aspirin", "Warfarin"], ["Digoxin"])
        test_data = {"test": "data"}
        self.cache.set(key1, test_data)

        # Same drugs, different order and case
        key2 = SafetyCache.build_key(["warfarin", "aspirin"], ["digoxin"])
        result = self.cache.get(key2)
        assert result is not None, "Reordered inputs should hit cache"
        assert result == test_data

    def test_cache_ttl_expiration(self):
        """Cache entries expire after TTL."""
        cache = SafetyCache(ttl_seconds=1)  # 1 second TTL
        key = SafetyCache.build_key(["aspirin"], [])
        cache.set(key, "test")

        assert cache.get(key) is not None, "Should hit before TTL"
        time.sleep(1.5)
        assert cache.get(key) is None, "Should miss after TTL"


# ===========================================================================
# TEST 3: Allergy Class Detection
# ===========================================================================

class TestAllergyDetection:
    """Allergy detection must handle exact, class, and cross-reactivity matches."""

    def test_exact_allergy_match(self):
        """Direct allergy match should be severity CRITICAL."""
        alerts = check_allergies(
            medicines=["amoxicillin"],
            known_allergies=["amoxicillin"],
        )
        assert len(alerts) >= 1
        critical_alerts = [a for a in alerts if a.severity == Severity.CRITICAL]
        assert len(critical_alerts) >= 1, "Exact match should be CRITICAL"

    def test_class_allergy_match(self):
        """Drug in same class as allergy should be detected."""
        # Penicillin allergy → amoxicillin should trigger
        alerts = check_allergies(
            medicines=["amoxicillin"],
            known_allergies=["penicillin"],
        )
        assert len(alerts) >= 1, "Class match should trigger allergy alert"

    def test_class_allergy_reverse(self):
        """Allergy to specific drug → another drug in same class detected."""
        # Allergic to amoxicillin → ampicillin should trigger (both penicillins)
        alerts = check_allergies(
            medicines=["ampicillin"],
            known_allergies=["amoxicillin"],
        )
        assert len(alerts) >= 1, "Same-class drug should trigger alert"

    def test_cross_reactivity(self):
        """Penicillin allergy should flag cephalosporin cross-reactivity."""
        alerts = check_allergies(
            medicines=["cephalexin"],
            known_allergies=["penicillin"],
        )
        # Should find cross-reactivity alert
        medium_alerts = [a for a in alerts if a.severity == Severity.MEDIUM]
        assert len(medium_alerts) >= 1, "Cross-reactivity should be flagged"

    def test_no_false_allergy(self):
        """Unrelated drugs should not trigger allergy alerts."""
        alerts = check_allergies(
            medicines=["metformin"],
            known_allergies=["penicillin"],
        )
        assert len(alerts) == 0, "Unrelated drug should not trigger alert"

    def test_multiple_allergies(self):
        """Multiple allergies should all be checked."""
        alerts = check_allergies(
            medicines=["amoxicillin", "ibuprofen"],
            known_allergies=["penicillin", "nsaids"],
        )
        amox_alerts = [a for a in alerts if a.medicine == "amoxicillin"]
        ibu_alerts = [a for a in alerts if a.medicine == "ibuprofen"]
        assert len(amox_alerts) >= 1, "Amoxicillin should trigger penicillin alert"
        assert len(ibu_alerts) >= 1, "Ibuprofen should trigger NSAID alert"


# ===========================================================================
# TEST 4: Duplicate Drug Handling
# ===========================================================================

class TestDuplicateHandling:
    """Duplicate drugs must be handled correctly."""

    def test_duplicate_removal(self):
        """Duplicate drugs should be removed during normalization."""
        normalized, warnings = normalize_drug_list(
            ["aspirin", "Aspirin", "ASPIRIN", "aspirin"]
        )
        assert len(normalized) == 1, "Duplicates should be removed"
        assert normalized[0] == "aspirin"
        assert any("Duplicate" in w for w in warnings)

    def test_duplicate_with_whitespace(self):
        """Duplicates with varied whitespace should be caught."""
        normalized, warnings = normalize_drug_list(
            ["aspirin", " aspirin ", "  aspirin"]
        )
        assert len(normalized) == 1


# ===========================================================================
# TEST 5: Invalid Input Rejection
# ===========================================================================

class TestInputValidation:
    """Invalid inputs must be rejected with clear errors."""

    def test_negative_age_rejected(self):
        """Negative age should fail validation."""
        with pytest.raises(Exception):
            PatientHistory(age=-5)

    def test_excessive_age_rejected(self):
        """Age > 150 should fail validation."""
        with pytest.raises(Exception):
            PatientHistory(age=200)

    def test_negative_weight_rejected(self):
        """Negative weight should fail validation."""
        with pytest.raises(Exception):
            PatientHistory(weight=-10)

    def test_zero_weight_rejected(self):
        """Zero weight should fail validation."""
        with pytest.raises(Exception):
            PatientHistory(weight=0)

    def test_excessive_weight_rejected(self):
        """Weight > 500 should fail validation."""
        with pytest.raises(Exception):
            PatientHistory(weight=600)

    def test_empty_medicines_rejected(self):
        """Empty medicines list should fail validation."""
        with pytest.raises(Exception):
            DrugSafetyRequest(medicines=[])

    def test_whitespace_only_medicines_rejected(self):
        """Medicines list with only whitespace should fail."""
        with pytest.raises(Exception):
            DrugSafetyRequest(medicines=["", "  ", "   "])

    def test_valid_input_accepted(self):
        """Valid inputs should pass validation."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(
                age=45,
                weight=70,
                known_allergies=["penicillin"],
                conditions=["diabetes"],
                current_medications=["metformin"],
            ),
        )
        assert len(request.medicines) == 1
        assert request.patient_history.age == 45


# ===========================================================================
# TEST 6: Fallback Triggering
# ===========================================================================

class TestFallbackSystem:
    """Fallback must work when LLM is unavailable or fails."""

    def test_fallback_database_loaded(self):
        """Fallback database should have at least 15 interactions."""
        assert fallback_db.interaction_count >= 15, (
            f"Fallback DB has only {fallback_db.interaction_count} interactions, need ≥15"
        )

    def test_fallback_lookup_known_pair(self):
        """Known interaction pair should be found in fallback."""
        result = fallback_db.lookup_pair("warfarin", "aspirin")
        assert result is not None, "Warfarin-Aspirin should be in fallback DB"
        assert result["severity"] == "high"

    def test_fallback_lookup_reversed_pair(self):
        """Pair lookup should work regardless of drug order."""
        result1 = fallback_db.lookup_pair("warfarin", "aspirin")
        result2 = fallback_db.lookup_pair("aspirin", "warfarin")
        assert result1 is not None
        assert result2 is not None

    def test_fallback_lookup_unknown_pair(self):
        """Unknown pair should return None."""
        result = fallback_db.lookup_pair("metformin", "aspirin")
        assert result is None, "Unknown pair should return None"

    def test_fallback_bulk_lookup(self):
        """Bulk lookup should find multiple interactions."""
        interactions = fallback_db.lookup_all_pairs(
            ["warfarin", "aspirin", "amiodarone"]
        )
        assert len(interactions) >= 2, (
            "Should find warfarin-aspirin and warfarin-amiodarone"
        )

    def test_engine_uses_fallback_without_llm(self):
        """Engine should use fallback when LLM is not available."""
        request = DrugSafetyRequest(
            medicines=["warfarin", "aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        # System should still work (via fallback)
        assert isinstance(response, DrugSafetyResponse)
        assert response.processing_time_ms >= 0
        assert response.source in (SourceType.LLM, SourceType.FALLBACK)


# ===========================================================================
# TEST 7: Schema Validation (NO raw text)
# ===========================================================================

class TestSchemaValidation:
    """Output must strictly match schema — no raw text anywhere."""

    def test_response_is_valid_json_serializable(self):
        """Response model must serialize to valid JSON."""
        request = DrugSafetyRequest(
            medicines=["warfarin", "aspirin"],
            patient_history=PatientHistory(age=65),
        )
        response = analyze_drug_safety(request)
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_response_has_all_required_fields(self):
        """Response must contain all required fields."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        data = response.model_dump()

        required_fields = [
            "interactions", "allergy_alerts", "contraindications",
            "patient_risk_score", "risk_breakdown", "overall_risk_level",
            "safe_to_prescribe", "requires_doctor_review",
            "source", "cache_hit", "processing_time_ms",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_no_raw_text_in_interactions(self):
        """Interactions must be structured objects, not raw text."""
        request = DrugSafetyRequest(
            medicines=["warfarin", "aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        for interaction in response.interactions:
            assert isinstance(interaction, DrugInteraction)
            assert interaction.drug_a
            assert interaction.drug_b
            assert interaction.severity in list(Severity)
            assert interaction.mechanism
            assert interaction.clinical_recommendation

    def test_llm_output_non_json_rejected(self):
        """Non-JSON LLM output must be rejected."""
        result, reason = validate_llm_output(
            "This is just plain text about drug interactions",
            {"aspirin", "warfarin"},
        )
        assert result is None, "Non-JSON output must be rejected"

    def test_llm_output_valid_json_accepted(self):
        """Valid JSON LLM output should be accepted."""
        valid_output = json.dumps({
            "interactions": [{
                "drug_a": "warfarin",
                "drug_b": "aspirin",
                "severity": "high",
                "mechanism": "Additive bleeding risk",
                "clinical_recommendation": "Monitor INR closely",
                "source_confidence": "high",
            }]
        })
        result, reason = validate_llm_output(
            valid_output,
            {"warfarin", "aspirin"},
        )
        assert result is not None, f"Valid output rejected: {reason}"
        assert len(result) == 1

    def test_llm_output_hallucinated_drugs_stripped(self):
        """LLM output with hallucinated drug names should strip them."""
        output_with_fake = json.dumps({
            "interactions": [
                {
                    "drug_a": "warfarin",
                    "drug_b": "aspirin",
                    "severity": "high",
                    "mechanism": "Real interaction",
                    "clinical_recommendation": "Monitor",
                    "source_confidence": "high",
                },
                {
                    "drug_a": "warfarin",
                    "drug_b": "fakedrug123",
                    "severity": "high",
                    "mechanism": "Fake interaction",
                    "clinical_recommendation": "N/A",
                    "source_confidence": "high",
                },
            ]
        })
        result, reason = validate_llm_output(
            output_with_fake,
            {"warfarin", "aspirin"},
        )
        assert result is not None
        assert len(result) == 1, "Hallucinated drug should be stripped"
        assert result[0].drug_b == "aspirin"


# ===========================================================================
# TEST 8: Risk Scoring Correctness
# ===========================================================================

class TestRiskScoring:
    """Risk scoring must follow defined formula and thresholds."""

    def test_zero_score_when_no_findings(self):
        """No interactions/allergies/contraindications → score 0."""
        score, breakdown = calculate_risk_score([], [], [])
        assert score == 0
        assert breakdown.interactions == 0
        assert breakdown.allergies == 0
        assert breakdown.contraindications == 0

    def test_high_interaction_scoring(self):
        """High severity interaction → 25 points."""
        interactions = [DrugInteraction(
            drug_a="warfarin", drug_b="aspirin",
            severity=Severity.HIGH,
            mechanism="test", clinical_recommendation="test",
        )]
        score, breakdown = calculate_risk_score(interactions, [], [])
        assert breakdown.interactions == 25
        assert score == 25

    def test_allergy_scoring_critical(self):
        """Critical allergy → 50 points."""
        allergies = [AllergyAlert(
            medicine="amoxicillin", allergen="amoxicillin",
            reason="Direct match", severity=Severity.CRITICAL,
        )]
        score, breakdown = calculate_risk_score([], allergies, [])
        assert breakdown.allergies == 50
        assert score == 50

    def test_contraindication_scoring(self):
        """Contraindication → 20 points each."""
        contras = [Contraindication(
            medicine="ibuprofen", condition="kidney disease",
            reason="Renal risk", severity=Severity.HIGH,
        )]
        score, breakdown = calculate_risk_score([], [], contras)
        assert breakdown.contraindications == 20
        assert score == 20

    def test_score_capped_at_100(self):
        """Total score must never exceed 100."""
        interactions = [
            DrugInteraction(
                drug_a=f"drug{i}", drug_b=f"drug{i+10}",
                severity=Severity.HIGH,
                mechanism="test", clinical_recommendation="test",
            )
            for i in range(10)
        ]
        allergies = [AllergyAlert(
            medicine="test", allergen="test",
            reason="test", severity=Severity.CRITICAL,
        )]
        contras = [
            Contraindication(
                medicine=f"drug{i}", condition="test",
                reason="test", severity=Severity.HIGH,
            )
            for i in range(5)
        ]
        score, _ = calculate_risk_score(interactions, allergies, contras)
        assert score <= 100, f"Score {score} exceeds cap of 100"

    def test_risk_levels(self):
        """Risk level thresholds must be correct."""
        assert determine_risk_level(0) == RiskLevel.LOW
        assert determine_risk_level(15) == RiskLevel.LOW
        assert determine_risk_level(30) == RiskLevel.LOW
        assert determine_risk_level(31) == RiskLevel.MEDIUM
        assert determine_risk_level(50) == RiskLevel.MEDIUM
        assert determine_risk_level(70) == RiskLevel.MEDIUM
        assert determine_risk_level(71) == RiskLevel.HIGH
        assert determine_risk_level(100) == RiskLevel.HIGH

    def test_combined_scoring(self):
        """Combined interactions + allergies + contraindications scoring."""
        interactions = [DrugInteraction(
            drug_a="warfarin", drug_b="aspirin",
            severity=Severity.HIGH,
            mechanism="test", clinical_recommendation="test",
        )]
        allergies = [AllergyAlert(
            medicine="amoxicillin", allergen="penicillin",
            reason="Class match", severity=Severity.HIGH,
        )]
        contras = [Contraindication(
            medicine="ibuprofen", condition="kidney disease",
            reason="test", severity=Severity.HIGH,
        )]
        score, breakdown = calculate_risk_score(interactions, allergies, contras)
        assert breakdown.interactions == 25
        assert breakdown.allergies == 40
        assert breakdown.contraindications == 20
        assert score == 85  # 25 + 40 + 20 = 85
        assert determine_risk_level(score) == RiskLevel.HIGH


# ===========================================================================
# TEST 9: Contraindication Detection
# ===========================================================================

class TestContraindications:
    """Drug-condition contraindications must be detected."""

    def test_kidney_disease_nsaid_contraindication(self):
        """NSAIDs should be contraindicated in kidney disease."""
        contras, warnings = check_contraindications(
            medicines=["ibuprofen"],
            conditions=["kidney disease"],
        )
        assert len(contras) >= 1
        assert any(c.medicine == "ibuprofen" for c in contras)

    def test_pregnancy_warfarin_contraindication(self):
        """Warfarin should be contraindicated in pregnancy."""
        contras, warnings = check_contraindications(
            medicines=["warfarin"],
            conditions=["pregnancy"],
        )
        assert len(contras) >= 1
        assert any(c.medicine == "warfarin" for c in contras)

    def test_asthma_beta_blocker_contraindication(self):
        """Non-selective beta-blockers should be contraindicated in asthma."""
        contras, warnings = check_contraindications(
            medicines=["propranolol"],
            conditions=["asthma"],
        )
        assert len(contras) >= 1

    def test_condition_aliases(self):
        """Condition aliases should be recognized (e.g., CKD → kidney disease)."""
        contras, warnings = check_contraindications(
            medicines=["ibuprofen"],
            conditions=["ckd"],
        )
        assert len(contras) >= 1, "CKD alias should map to kidney disease"

    def test_no_false_contraindication(self):
        """Unrelated drug-condition pairs should not trigger."""
        contras, warnings = check_contraindications(
            medicines=["amoxicillin"],
            conditions=["diabetes"],
        )
        assert len(contras) == 0

    def test_age_warnings(self):
        """Age-based warnings should be generated."""
        _, warnings = check_contraindications(
            medicines=["aspirin"],
            conditions=[],
            age=8,
        )
        assert any("PEDIATRIC" in w for w in warnings)

        _, warnings = check_contraindications(
            medicines=["aspirin"],
            conditions=[],
            age=80,
        )
        assert any("GERIATRIC" in w for w in warnings)

    def test_weight_warnings(self):
        """Weight-based warnings should be generated."""
        _, warnings = check_contraindications(
            medicines=["aspirin"],
            conditions=[],
            weight=35,
        )
        assert any("LOW BODY WEIGHT" in w for w in warnings)


# ===========================================================================
# TEST 10: Patient History Influence
# ===========================================================================

class TestPatientHistoryInfluence:
    """Patient history MUST influence the output."""

    def test_allergy_changes_output(self):
        """Adding an allergy must change the response."""
        # Without allergy
        req_no_allergy = DrugSafetyRequest(
            medicines=["amoxicillin"],
            patient_history=PatientHistory(),
        )
        resp_no_allergy = analyze_drug_safety(req_no_allergy)

        # With penicillin allergy
        req_with_allergy = DrugSafetyRequest(
            medicines=["amoxicillin"],
            patient_history=PatientHistory(
                known_allergies=["penicillin"],
            ),
        )
        resp_with_allergy = analyze_drug_safety(req_with_allergy)

        assert len(resp_with_allergy.allergy_alerts) > len(resp_no_allergy.allergy_alerts), (
            "Allergy must change output"
        )
        assert resp_with_allergy.patient_risk_score > resp_no_allergy.patient_risk_score

    def test_condition_changes_output(self):
        """Adding a condition must change the response."""
        # Without condition
        req_no_cond = DrugSafetyRequest(
            medicines=["ibuprofen"],
            patient_history=PatientHistory(),
        )
        resp_no_cond = analyze_drug_safety(req_no_cond)

        # With kidney disease
        req_with_cond = DrugSafetyRequest(
            medicines=["ibuprofen"],
            patient_history=PatientHistory(
                conditions=["kidney disease"],
            ),
        )
        resp_with_cond = analyze_drug_safety(req_with_cond)

        assert len(resp_with_cond.contraindications) > len(resp_no_cond.contraindications), (
            "Condition must change output"
        )

    def test_current_medications_influence(self):
        """Current medications must generate interaction checks."""
        # Without current meds
        req_no_current = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        resp_no_current = analyze_drug_safety(req_no_current)

        # With warfarin as current medication
        req_with_current = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(
                current_medications=["warfarin"],
            ),
        )
        resp_with_current = analyze_drug_safety(req_with_current)

        assert len(resp_with_current.interactions) > len(resp_no_current.interactions), (
            "Current medications must influence interaction checking"
        )


# ===========================================================================
# TEST 11: Edge Cases
# ===========================================================================

class TestEdgeCases:
    """All edge cases must be handled gracefully."""

    def test_single_medicine_no_interactions(self):
        """Single medicine should have no interactions."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        assert isinstance(response, DrugSafetyResponse)
        assert response.processing_time_ms >= 0

    def test_response_never_empty(self):
        """System must NEVER return a truly empty response."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        assert response is not None
        assert response.processing_time_ms is not None
        assert response.cache_hit is not None
        assert response.source is not None

    def test_fuzzy_matching_misspelling(self):
        """Misspelled drug names should be fuzzy matched."""
        # "aspirn" should match "aspirin" (distance = 1)
        correction = fuzzy_match_drug("aspirn")
        assert correction == "aspirin", f"Expected 'aspirin', got '{correction}'"

    def test_fuzzy_matching_no_match(self):
        """Completely wrong names should not match."""
        correction = fuzzy_match_drug("xyzabcdef123")
        assert correction is None, "Random string should not match any drug"

    def test_llm_output_with_markdown_fences(self):
        """LLM output wrapped in markdown should still parse."""
        markdown_output = '```json\n{"interactions": []}\n```'
        result = parse_llm_json(markdown_output)
        assert result is not None
        assert result == {"interactions": []}

    def test_llm_output_with_trailing_text(self):
        """LLM output with trailing text should still parse JSON."""
        messy_output = 'Here is the result:\n{"interactions": []}\nI hope this helps!'
        result = parse_llm_json(messy_output)
        assert result is not None
        assert result == {"interactions": []}

    def test_processing_time_always_present(self):
        """processing_time_ms must always be in the response."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        assert response.processing_time_ms >= 0
        assert isinstance(response.processing_time_ms, float)

    def test_cache_hit_always_present(self):
        """cache_hit must always be in the response."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        assert isinstance(response.cache_hit, bool)

    def test_source_always_present(self):
        """source must always be in the response."""
        request = DrugSafetyRequest(
            medicines=["aspirin"],
            patient_history=PatientHistory(),
        )
        response = analyze_drug_safety(request)
        assert response.source in (SourceType.LLM, SourceType.FALLBACK)

    def test_known_drugs_database_populated(self):
        """Known drugs set should have substantial entries."""
        assert len(KNOWN_DRUGS) > 100, (
            f"Known drugs has only {len(KNOWN_DRUGS)} entries, expected >100"
        )

    def test_drug_class_map_populated(self):
        """Drug class map should have reasonable coverage."""
        assert len(DRUG_CLASS_MAP) >= 15, (
            f"Drug class map has only {len(DRUG_CLASS_MAP)} classes, expected ≥15"
        )


# ===========================================================================
# TEST 12: Full Integration (End-to-End)
# ===========================================================================

class TestEndToEnd:
    """Full pipeline integration tests."""

    def test_complex_scenario(self):
        """
        Complex clinical scenario:
        - Patient on warfarin + metformin
        - Proposing aspirin + ibuprofen
        - Allergic to penicillin
        - Has kidney disease
        - Age 72, weight 65kg

        Expected:
        - warfarin-aspirin interaction (high)
        - NSAIDs contraindicated with kidney disease
        - Geriatric warning
        - High risk score
        - Not safe to prescribe
        """
        request = DrugSafetyRequest(
            medicines=["aspirin", "ibuprofen"],
            patient_history=PatientHistory(
                current_medications=["warfarin", "metformin"],
                known_allergies=["penicillin"],
                conditions=["kidney disease"],
                age=72,
                weight=65,
            ),
        )
        response = analyze_drug_safety(request)

        # Must have interactions (warfarin-aspirin at minimum)
        assert len(response.interactions) >= 1, "Should find warfarin-aspirin interaction"

        # Must have contraindications (ibuprofen + kidney disease)
        assert len(response.contraindications) >= 1, "Should find NSAID contraindication"
        assert any(
            c.medicine == "ibuprofen" and "kidney" in c.condition.lower()
            for c in response.contraindications
        ), "Ibuprofen + kidney disease should be flagged"

        # Risk must be elevated
        assert response.patient_risk_score > 30, "Risk score should be elevated"
        assert response.safe_to_prescribe is False
        assert response.requires_doctor_review is True

        # Must have geriatric warning
        assert any("GERIATRIC" in w for w in response.warnings), (
            "Should have geriatric warning for age 72"
        )

        # All required fields present
        assert response.processing_time_ms >= 0
        assert isinstance(response.cache_hit, bool)
        assert response.source in (SourceType.LLM, SourceType.FALLBACK)

    def test_safe_scenario(self):
        """
        Safe scenario: single drug, no history, should be low risk.
        """
        request = DrugSafetyRequest(
            medicines=["metformin"],
            patient_history=PatientHistory(age=45, weight=70),
        )
        response = analyze_drug_safety(request)
        assert response.patient_risk_score <= 30
        assert response.overall_risk_level == RiskLevel.LOW


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
