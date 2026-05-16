"""
Clinical Notes Parser — Endpoint for parsing free-text clinical notes.

Uses the Groq LLM (when available) to extract structured medical entities
from free-text clinical notes. Falls back to heuristic parsing when the
LLM is unavailable.

Endpoint: POST /api/v1/clinical-notes/parse
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from llm_interface import llm


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class ClinicalNoteRequest(BaseModel):
    """Request body for clinical note parsing."""
    note: str = Field(..., min_length=1, description="Free-text clinical note to parse")


class ClinicalNoteResponse(BaseModel):
    """Structured entities extracted from a clinical note."""
    medicines: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    age: Optional[int] = None
    weight: Optional[float] = None
    question: Optional[str] = None
    source: str = "Heuristic"


# ---------------------------------------------------------------------------
# Heuristic Parser (local fallback)
# ---------------------------------------------------------------------------

COMMON_DRUGS = [
    "aspirin", "ibuprofen", "warfarin", "metformin", "lisinopril", "atorvastatin",
    "amoxicillin", "penicillin", "clopidogrel", "heparin", "naproxen", "paracetamol",
    "acetaminophen", "amlodipine", "omeprazole", "simvastatin", "losartan",
    "ciprofloxacin", "azithromycin", "prednisone", "insulin", "digoxin",
    "furosemide", "metoprolol", "tramadol", "morphine", "codeine", "diazepam",
    "propranolol", "verapamil", "diltiazem", "amiodarone", "clarithromycin",
    "methotrexate", "lithium", "carbamazepine", "phenytoin", "rifampin",
    "fluconazole", "ketoconazole", "erythromycin", "doxycycline", "gabapentin",
    "pregabalin", "sertraline", "fluoxetine", "paroxetine", "citalopram",
    "escitalopram", "venlafaxine", "duloxetine", "mirtazapine", "trazodone",
    "haloperidol", "risperidone", "quetiapine", "olanzapine", "clozapine",
    "hydrochlorothiazide", "spironolactone", "enalapril", "ramipril",
    "candesartan", "valsartan", "rosuvastatin", "pravastatin",
]

COMMON_CONDITIONS = [
    "hypertension", "diabetes", "asthma", "ckd", "kidney disease", "liver disease",
    "pregnancy", "heart failure", "copd", "epilepsy", "depression", "anxiety",
    "ulcer", "gerd", "stroke", "arrhythmia", "atrial fibrillation",
    "hypothyroidism", "hyperthyroidism", "gout", "osteoporosis",
]

COMMON_ALLERGENS = [
    "penicillin", "sulfa", "aspirin", "latex", "iodine", "nsaid", "nsaids",
    "cephalosporin", "sulfonamide", "codeine", "morphine",
]


def _find_tokens(text: str, vocabulary: list[str]) -> list[str]:
    """Find known vocabulary terms in text using word boundary matching."""
    lower = text.lower()
    found = []
    for term in vocabulary:
        pattern = r'\b' + re.escape(term) + r'\b'
        if re.search(pattern, lower, re.IGNORECASE):
            found.append(term)
    return list(set(found))


def _extract_age(text: str) -> Optional[int]:
    """Extract patient age from text."""
    m = (
        re.search(r'\b(\d{1,3})\s*(?:y/?o|yo|years?\s*old|year-old)\b', text, re.I)
        or re.search(r'\bage[:\s]+(\d{1,3})\b', text, re.I)
    )
    if m:
        n = int(m.group(1))
        if 0 < n < 130:
            return n
    return None


def _extract_weight(text: str) -> Optional[float]:
    """Extract patient weight from text."""
    m = re.search(r'\b(\d{1,3}(?:\.\d+)?)\s*kg\b', text, re.I)
    if m:
        n = float(m.group(1))
        if 0 < n < 400:
            return n
    return None


def heuristic_parse(note: str) -> ClinicalNoteResponse:
    """Parse a clinical note using heuristic rules (no LLM needed)."""
    text = note

    # Classify drugs as proposed vs current
    proposed_match = re.search(
        r'\b(?:give|start|prescribe|add|consider)\s+([a-z][a-z\-\s,]+)', text, re.I
    )
    on_match = re.search(
        r'\b(?:on|taking|takes|currently on)\s+([a-z][a-z\-\s,]+)', text, re.I
    )

    all_drugs = _find_tokens(text, COMMON_DRUGS)
    proposed = _find_tokens(proposed_match.group(1), COMMON_DRUGS) if proposed_match else []
    on_meds = _find_tokens(on_match.group(1), COMMON_DRUGS) if on_match else []

    classified = set(proposed + on_meds)
    unclassified = [d for d in all_drugs if d not in classified]

    medicines = list(set(proposed + (unclassified if not proposed else [])))
    current_medications = list(set(on_meds + (unclassified if proposed else [])))

    conditions = _find_tokens(text, COMMON_CONDITIONS)

    # Allergies
    allergy_match = re.search(
        r'\b(?:allergic to|allergy to|allergies?)[:\s]+([a-z,\s]+)', text, re.I
    )
    allergies = _find_tokens(allergy_match.group(1), COMMON_ALLERGENS) if allergy_match else []

    return ClinicalNoteResponse(
        medicines=medicines,
        current_medications=current_medications,
        conditions=conditions,
        allergies=allergies,
        age=_extract_age(text),
        weight=_extract_weight(text),
        question=text.strip(),
        source="Heuristic",
    )


# ---------------------------------------------------------------------------
# LLM-based Parser
# ---------------------------------------------------------------------------

_PARSE_SYSTEM_PROMPT = """You are a clinical NLP assistant. Extract structured medical entities from the clinical note.

Return ONLY valid JSON with this exact schema:
{
  "medicines": ["proposed/new drugs"],
  "current_medications": ["drugs patient is already taking"],
  "conditions": ["medical conditions mentioned"],
  "allergies": ["known drug allergies"],
  "age": null or integer,
  "weight": null or float in kg,
  "question": "the clinical question or note summary"
}

Rules:
- Use lowercase drug names
- Only include entities explicitly mentioned in the note
- If a field has no data, use an empty array [] or null
- Respond with ONLY the JSON object. No explanation."""


def llm_parse(note: str) -> Optional[ClinicalNoteResponse]:
    """Try to parse a clinical note using the LLM. Returns None on failure."""
    if not llm.is_available or llm._client is None:
        return None

    try:
        response = llm._client.chat.completions.create(
            model=llm._model_info.get("model", "llama-3.3-70b-versatile"),
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Parse this clinical note:\n\n{note}"},
            ],
            temperature=0.1,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            return None

        data = json.loads(content)

        return ClinicalNoteResponse(
            medicines=[m.lower().strip() for m in data.get("medicines", []) if m],
            current_medications=[m.lower().strip() for m in data.get("current_medications", []) if m],
            conditions=[c.lower().strip() for c in data.get("conditions", []) if c],
            allergies=[a.lower().strip() for a in data.get("allergies", []) if a],
            age=data.get("age") if isinstance(data.get("age"), (int, float)) else _extract_age(note),
            weight=data.get("weight") if isinstance(data.get("weight"), (int, float)) else _extract_weight(note),
            question=data.get("question", note.strip()),
            source="LLM",
        )
    except Exception as e:
        print(f"WARNING: LLM clinical note parsing failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_clinical_note(note: str) -> ClinicalNoteResponse:
    """
    Parse a clinical note — tries LLM first, falls back to heuristic.
    """
    # Try LLM first
    result = llm_parse(note)
    if result is not None:
        return result

    # Fallback to heuristic
    return heuristic_parse(note)
