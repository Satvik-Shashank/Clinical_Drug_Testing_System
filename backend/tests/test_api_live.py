"""
Live API verification tests for the Clinical Drug Safety Engine.
Run with: python tests/test_api_live.py
Requires the server to be running on localhost:8000
"""

import json
import sys
import requests

# Fix Windows console encoding for Unicode characters
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000"


def test_complex_scenario():
    """TEST 1: Complex clinical scenario."""
    print("=" * 60)
    print("TEST 1: Complex clinical scenario")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["aspirin", "ibuprofen"],
        "patient_history": {
            "current_medications": ["warfarin", "metformin"],
            "known_allergies": ["penicillin"],
            "conditions": ["kidney disease"],
            "age": 72,
            "weight": 65
        }
    })
    d = r.json()
    assert r.status_code == 200, "Status should be 200"
    print("  Interactions:", len(d["interactions"]))
    print("  Contraindications:", len(d["contraindications"]))
    print("  Risk score:", d["patient_risk_score"])
    print("  Risk level:", d["overall_risk_level"])
    print("  Safe to prescribe:", d["safe_to_prescribe"])
    print("  Doctor review:", d["requires_doctor_review"])
    print("  Source:", d["source"])
    print("  Cache hit:", d["cache_hit"])
    print("  Processing time:", d["processing_time_ms"], "ms")
    print("  Warnings:", d["warnings"])

    for inter in d["interactions"]:
        print("    INTERACTION:", inter["drug_a"], "+", inter["drug_b"], "->", inter["severity"])

    for contra in d["contraindications"]:
        print("    CONTRA:", contra["medicine"], "+", contra["condition"], "->", contra["severity"])

    assert len(d["interactions"]) >= 1, "Should find warfarin-aspirin interaction"
    assert len(d["contraindications"]) >= 2, "Should find NSAID + aspirin contraindications for kidney disease"
    assert d["safe_to_prescribe"] is False, "Should not be safe"
    assert d["requires_doctor_review"] is True, "Should require review"
    assert d["processing_time_ms"] > 0, "Processing time should be > 0"
    assert d["cache_hit"] is False, "First call should be cache miss"
    assert any("GERIATRIC" in w for w in d["warnings"]), "Should have geriatric warning"
    print("  PASSED")
    return d["processing_time_ms"]


def test_cache_hit():
    """TEST 2: Cache hit with reordered + different case inputs."""
    print()
    print("=" * 60)
    print("TEST 2: Cache hit (reordered + different case)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["IBUPROFEN", "Aspirin"],
        "patient_history": {
            "current_medications": ["Metformin", "WARFARIN"],
            "known_allergies": ["penicillin"],
            "conditions": ["kidney disease"],
            "age": 72,
            "weight": 65
        }
    })
    d = r.json()
    print("  Cache hit:", d["cache_hit"])
    print("  Processing time:", d["processing_time_ms"], "ms")
    assert d["cache_hit"] is True, "Should be cache hit on reordered inputs"
    print("  PASSED")


def test_allergy_class_detection():
    """TEST 3: Allergy class matching + cross-reactivity."""
    print()
    print("=" * 60)
    print("TEST 3: Allergy class detection (penicillin -> amoxicillin + cephalexin)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["amoxicillin", "cephalexin"],
        "patient_history": {
            "known_allergies": ["penicillin"]
        }
    })
    d = r.json()
    print("  Allergy alerts:", len(d["allergy_alerts"]))
    for a in d["allergy_alerts"]:
        print("    ALERT:", a["medicine"], "->", a["allergen"], "(" + a["severity"] + ")")
        print("      Reason:", a["reason"])

    assert len(d["allergy_alerts"]) >= 2, "Should detect amoxicillin class match + cephalexin cross-reactivity"
    amox_alerts = [a for a in d["allergy_alerts"] if a["medicine"] == "amoxicillin"]
    ceph_alerts = [a for a in d["allergy_alerts"] if a["medicine"] == "cephalexin"]
    assert len(amox_alerts) >= 1, "Amoxicillin should trigger penicillin class alert"
    assert len(ceph_alerts) >= 1, "Cephalexin should trigger cross-reactivity alert"
    assert d["safe_to_prescribe"] is False, "Should not be safe with allergy alerts"
    print("  PASSED")


def test_negative_age_rejected():
    """TEST 4: Negative age -> 422."""
    print()
    print("=" * 60)
    print("TEST 4: Invalid input rejection (negative age)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["aspirin"],
        "patient_history": {"age": -5}
    })
    print("  Status:", r.status_code)
    assert r.status_code == 422, "Should reject negative age with 422"
    print("  PASSED")


def test_fuzzy_matching():
    """TEST 5: Misspelled drug fuzzy matching."""
    print()
    print("=" * 60)
    print("TEST 5: Misspelled drug fuzzy matching (warfrin, aspirn)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["warfrin", "aspirn"],
        "patient_history": {}
    })
    d = r.json()
    print("  Warnings:", d["warnings"])
    print("  Interactions found:", len(d["interactions"]))
    has_correction = any("corrected" in w.lower() or "misspelling" in w.lower() for w in d["warnings"])
    print("  Fuzzy match warning:", has_correction)
    assert has_correction, "Should have misspelling correction warnings"
    # After correction, warfarin+aspirin should have interaction
    assert len(d["interactions"]) >= 1, "Should find interaction after fuzzy correction"
    print("  PASSED")


def test_health_check():
    """TEST 6: Health check endpoint."""
    print()
    print("=" * 60)
    print("TEST 6: Health check")
    r = requests.get(BASE + "/health")
    d = r.json()
    print("  Status:", d["status"])
    print("  Mode:", d["mode"])
    print("  Components:", json.dumps(d["components"], indent=4))
    assert d["status"] == "healthy", "Health check should be healthy"
    print("  PASSED")


def test_empty_medicines():
    """TEST 7: Empty medicines -> 422."""
    print()
    print("=" * 60)
    print("TEST 7: Empty medicines rejection")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": [],
        "patient_history": {}
    })
    print("  Status:", r.status_code)
    assert r.status_code == 422, "Should reject empty medicines"
    print("  PASSED")


def test_safe_scenario():
    """TEST 8: Single safe drug, low risk."""
    print()
    print("=" * 60)
    print("TEST 8: Safe scenario (single drug, no history)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["metformin"],
        "patient_history": {"age": 45, "weight": 70}
    })
    d = r.json()
    print("  Risk score:", d["patient_risk_score"])
    print("  Risk level:", d["overall_risk_level"])
    print("  Safe:", d["safe_to_prescribe"])
    print("  Processing time:", d["processing_time_ms"], "ms")
    assert d["overall_risk_level"] == "low", "Single safe drug should be low risk"
    assert d["safe_to_prescribe"] is True, "Should be safe to prescribe"
    print("  PASSED")


def test_contraindication_pregnancy():
    """TEST 9: Pregnancy contraindications."""
    print()
    print("=" * 60)
    print("TEST 9: Pregnancy contraindications (warfarin + methotrexate)")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["warfarin", "methotrexate", "lisinopril"],
        "patient_history": {
            "conditions": ["pregnancy"],
            "age": 30
        }
    })
    d = r.json()
    print("  Contraindications:", len(d["contraindications"]))
    for c in d["contraindications"]:
        print("    CONTRA:", c["medicine"], "+", c["condition"], "->", c["severity"])

    assert len(d["contraindications"]) >= 3, "All 3 drugs should be contraindicated in pregnancy"
    assert d["safe_to_prescribe"] is False
    assert d["requires_doctor_review"] is True
    print("  PASSED")


def test_duplicate_handling():
    """TEST 10: Duplicate drugs are handled."""
    print()
    print("=" * 60)
    print("TEST 10: Duplicate drug handling")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["aspirin", "ASPIRIN", " aspirin ", "Aspirin"],
        "patient_history": {}
    })
    d = r.json()
    print("  Warnings:", d["warnings"])
    dup_warnings = [w for w in d["warnings"] if "Duplicate" in w or "duplicate" in w]
    print("  Duplicate warnings:", len(dup_warnings))
    assert len(dup_warnings) >= 1, "Should warn about duplicates"
    print("  PASSED")


def test_response_schema():
    """TEST 11: Full response schema validation."""
    print()
    print("=" * 60)
    print("TEST 11: Response schema completeness")
    r = requests.post(BASE + "/api/v1/drug-safety/check", json={
        "medicines": ["aspirin"],
        "patient_history": {}
    })
    d = r.json()
    required = [
        "interactions", "allergy_alerts", "contraindications",
        "patient_risk_score", "risk_breakdown", "overall_risk_level",
        "safe_to_prescribe", "requires_doctor_review",
        "source", "cache_hit", "processing_time_ms"
    ]
    missing = [f for f in required if f not in d]
    print("  All fields present:", len(missing) == 0)
    if missing:
        print("  Missing:", missing)
    assert len(missing) == 0, "All required fields must be present"

    # Verify risk_breakdown sub-fields
    rb = d["risk_breakdown"]
    assert "interactions" in rb, "risk_breakdown must have interactions"
    assert "allergies" in rb, "risk_breakdown must have allergies"
    assert "contraindications" in rb, "risk_breakdown must have contraindications"
    print("  PASSED")


def test_system_info():
    """TEST 12: System info endpoint."""
    print()
    print("=" * 60)
    print("TEST 12: System info")
    r = requests.get(BASE + "/api/v1/system-info")
    d = r.json()
    print("  Engine:", d["engine"])
    print("  Version:", d["version"])
    print("  LLM available:", d["llm"]["available"])
    print("  Fallback count:", d["fallback"]["interactions_count"])
    print("  Safety features:", len(d["safety_features"]))
    assert d["fallback"]["interactions_count"] >= 20, "Should have 20+ fallback interactions"
    print("  PASSED")


if __name__ == "__main__":
    try:
        t = test_complex_scenario()
        test_cache_hit()
        test_allergy_class_detection()
        test_negative_age_rejected()
        test_fuzzy_matching()
        test_health_check()
        test_empty_medicines()
        test_safe_scenario()
        test_contraindication_pregnancy()
        test_duplicate_handling()
        test_response_schema()
        test_system_info()

        print()
        print("=" * 60)
        print("ALL 12 API TESTS PASSED")
        print("Typical processing time:", t, "ms")
        print("=" * 60)

    except requests.ConnectionError:
        print("ERROR: Cannot connect to server at", BASE)
        print("Start the server first: python main.py")
        sys.exit(1)
    except AssertionError as e:
        print("ASSERTION FAILED:", e)
        sys.exit(1)
