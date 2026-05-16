"""
Clinical Drug Safety Engine — Pydantic Models

Strict type-safe models for request validation, response serialization,
and internal data transfer. All models enforce required fields and
constrained value ranges for clinical safety.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Drug interaction / allergy severity levels."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CRITICAL = "critical"  # Used for exact allergy matches


class RiskLevel(str, Enum):
    """Overall patient risk classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(str, Enum):
    """Indicates whether results came from LLM or fallback engine."""
    LLM = "llm"
    FALLBACK = "fallback"


class ConfidenceLevel(str, Enum):
    """LLM self-reported confidence in its output."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class PatientHistory(BaseModel):
    """Patient's medical history — ALL fields actively influence output."""
    current_medications: list[str] = Field(
        default_factory=list,
        description="Medications the patient is currently taking"
    )
    known_allergies: list[str] = Field(
        default_factory=list,
        description="Known drug allergies (exact names or drug classes)"
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Active medical conditions (e.g., kidney_disease, diabetes)"
    )
    age: Optional[int] = Field(
        default=None,
        description="Patient age in years"
    )
    weight: Optional[float] = Field(
        default=None,
        description="Patient weight in kg"
    )

    @field_validator("age")
    @classmethod
    def validate_age(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            if v < 0:
                raise ValueError("Age must be non-negative")
            if v > 150:
                raise ValueError("Age must be 150 or less")
        return v

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v <= 0:
                raise ValueError("Weight must be positive")
            if v > 500:
                raise ValueError("Weight must be 500 kg or less")
        return v


class DrugSafetyRequest(BaseModel):
    """
    Input request for drug safety analysis.
    
    medicines: list of proposed new medicines to evaluate
    patient_history: patient's current medical context
    """
    medicines: list[str] = Field(
        ...,
        min_length=1,
        description="Proposed new medicines to check (at least one required)"
    )
    patient_history: PatientHistory = Field(
        default_factory=PatientHistory,
        description="Patient's medical history"
    )

    @field_validator("medicines")
    @classmethod
    def validate_medicines_not_empty(cls, v: list[str]) -> list[str]:
        # Filter out empty/whitespace-only strings
        filtered = [m.strip() for m in v if m and m.strip()]
        if not filtered:
            raise ValueError("At least one non-empty medicine name is required")
        return filtered


# ---------------------------------------------------------------------------
# Response Sub-Models
# ---------------------------------------------------------------------------

class DrugInteraction(BaseModel):
    """A single drug-drug interaction finding."""
    drug_a: str = Field(..., description="First drug in the interaction pair")
    drug_b: str = Field(..., description="Second drug in the interaction pair")
    severity: Severity = Field(..., description="Interaction severity level")
    mechanism: str = Field(..., min_length=1, description="Pharmacological mechanism")
    clinical_recommendation: str = Field(
        ..., min_length=1,
        description="Clinical recommendation for managing this interaction"
    )
    source_confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.HIGH,
        description="Confidence level in this finding"
    )


class AllergyAlert(BaseModel):
    """An allergy alert triggered by patient's known allergies."""
    medicine: str = Field(..., description="The medicine triggering the alert")
    allergen: str = Field(..., description="The allergen that was matched")
    reason: str = Field(..., min_length=1, description="Why this alert was triggered")
    severity: Severity = Field(..., description="Alert severity")


class Contraindication(BaseModel):
    """A drug-condition contraindication finding."""
    medicine: str = Field(..., description="The contraindicated medicine")
    condition: str = Field(..., description="The condition creating the contraindication")
    reason: str = Field(..., min_length=1, description="Clinical reason")
    severity: Severity = Field(
        default=Severity.HIGH,
        description="Contraindication severity"
    )


class RiskBreakdown(BaseModel):
    """Numerical breakdown of risk score components."""
    interactions: int = Field(..., ge=0, le=100, description="Points from drug interactions")
    allergies: int = Field(..., ge=0, le=100, description="Points from allergy alerts")
    contraindications: int = Field(..., ge=0, le=100, description="Points from contraindications")


# ---------------------------------------------------------------------------
# Main Response Model
# ---------------------------------------------------------------------------

class DrugSafetyResponse(BaseModel):
    """
    Complete drug safety analysis response.
    
    STRICT SCHEMA — every field is required, no raw text anywhere.
    This is the ONLY output format the system ever returns.
    """
    interactions: list[DrugInteraction] = Field(
        default_factory=list,
        description="Drug-drug interactions found"
    )
    allergy_alerts: list[AllergyAlert] = Field(
        default_factory=list,
        description="Allergy alerts triggered"
    )
    contraindications: list[Contraindication] = Field(
        default_factory=list,
        description="Drug-condition contraindications"
    )
    patient_risk_score: int = Field(
        ..., ge=0, le=100,
        description="Aggregate risk score (0-100)"
    )
    risk_breakdown: RiskBreakdown = Field(
        ...,
        description="Numerical breakdown of risk score"
    )
    overall_risk_level: RiskLevel = Field(
        ...,
        description="Risk classification: low / medium / high"
    )
    safe_to_prescribe: bool = Field(
        ...,
        description="Whether it is safe to prescribe these medicines"
    )
    requires_doctor_review: bool = Field(
        ...,
        description="Whether a doctor must review before prescribing"
    )
    source: SourceType = Field(
        ...,
        description="Whether results came from LLM or fallback"
    )
    cache_hit: bool = Field(
        ...,
        description="Whether the interaction results were served from cache"
    )
    processing_time_ms: float = Field(
        ..., ge=0,
        description="Total processing time in milliseconds"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-critical warnings (e.g., misspelling corrections, age flags)"
    )


# ---------------------------------------------------------------------------
# Internal Models (LLM Output Parsing)
# ---------------------------------------------------------------------------

class LLMInteractionOutput(BaseModel):
    """Schema for parsing a single interaction from LLM JSON output."""
    drug_a: str = ""
    drug_b: str = ""
    severity: str = ""
    mechanism: str = ""
    clinical_recommendation: str = ""
    source_confidence: str = "high"


class LLMRawOutput(BaseModel):
    """Schema for parsing the complete LLM JSON response."""
    interactions: list[LLMInteractionOutput] = Field(default_factory=list)
