"""
Response Adapter — Transforms backend DrugSafetyResponse to frontend-expected format.

The frontend (React/TypeScript) expects a slightly different JSON shape than
what the backend Pydantic models produce. This adapter bridges that gap
WITHOUT changing either the internal models or the frontend components.

Mapping:
  Backend                            → Frontend
  ───────────────────────────────── → ──────────────────────────
  overall_risk_level: "high"         → overall_risk: "HIGH"
  allergy_alerts[].medicine          → allergies[].drug
  interactions[].clinical_recommendation → interactions[].recommendation
  contraindications[].medicine       → contraindications[].drug
  contraindications[].reason         → contraindications[].reasoning
  risk_breakdown.interactions        → risk_breakdown.interaction_risk
  risk_breakdown.allergies           → risk_breakdown.allergy_risk
  risk_breakdown.contraindications   → risk_breakdown.contraindication_risk
  source / cache_hit / processing_time_ms → system_info { source, cache_hit, processing_time_ms }
  warnings: ["string"]              → warnings: [{category, message}]
"""

from __future__ import annotations
from typing import Any

from models import DrugSafetyResponse


def adapt_response_for_frontend(response: DrugSafetyResponse) -> dict[str, Any]:
    """
    Convert a DrugSafetyResponse into the JSON shape the React frontend expects.
    """
    raw = response.model_dump()

    # --- Interactions ---
    interactions = []
    for it in raw.get("interactions", []):
        interactions.append({
            "drug_a": it["drug_a"],
            "drug_b": it["drug_b"],
            "severity": it["severity"].upper() if isinstance(it["severity"], str) else it["severity"],
            "mechanism": it["mechanism"],
            "recommendation": it.get("clinical_recommendation", ""),
        })

    # --- Allergies (allergy_alerts → allergies) ---
    allergies = []
    for al in raw.get("allergy_alerts", []):
        allergies.append({
            "drug": al["medicine"],
            "allergen": al["allergen"],
            "reason": al["reason"],
            "severity": al["severity"].upper() if isinstance(al["severity"], str) else al["severity"],
        })

    # --- Contraindications ---
    contraindications = []
    for ci in raw.get("contraindications", []):
        contraindications.append({
            "drug": ci["medicine"],
            "condition": ci["condition"],
            "reasoning": ci["reason"],
            "severity": ci["severity"].upper() if isinstance(ci["severity"], str) else ci["severity"],
        })

    # --- Risk breakdown ---
    rb = raw.get("risk_breakdown", {})
    risk_breakdown = {
        "interaction_risk": rb.get("interactions", 0),
        "allergy_risk": rb.get("allergies", 0),
        "contraindication_risk": rb.get("contraindications", 0),
    }

    # --- Warnings (string[] → {category, message}[]) ---
    warnings = []
    for w in raw.get("warnings", []):
        if isinstance(w, str):
            # Heuristic: extract category from known prefixes
            category = "special"
            if "GERIATRIC" in w.upper():
                category = "geriatric"
            elif "WEIGHT" in w.upper() or "PEDIATRIC" in w.upper():
                category = "weight"
            elif "MISSPELLING" in w.upper() or "FUZZY" in w.upper() or "corrected" in w.lower():
                category = "correction"
            warnings.append({"category": category, "message": w})
        elif isinstance(w, dict):
            warnings.append(w)

    # --- System info ---
    source_raw = raw.get("source", "fallback")
    system_info = {
        "source": "LLM" if source_raw == "llm" else "Fallback",
        "cache_hit": raw.get("cache_hit", False),
        "processing_time_ms": raw.get("processing_time_ms", 0),
    }

    # --- Overall risk ---
    overall_risk_raw = raw.get("overall_risk_level", "medium")
    overall_risk = overall_risk_raw.upper() if isinstance(overall_risk_raw, str) else "MEDIUM"

    return {
        "overall_risk": overall_risk,
        "patient_risk_score": raw.get("patient_risk_score", 0),
        "safe_to_prescribe": raw.get("safe_to_prescribe", False),
        "requires_doctor_review": raw.get("requires_doctor_review", True),
        "interactions": interactions,
        "allergies": allergies,
        "contraindications": contraindications,
        "risk_breakdown": risk_breakdown,
        "warnings": warnings,
        "system_info": system_info,
    }
