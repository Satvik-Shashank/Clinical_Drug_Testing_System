"""
Clinical Drug Safety Engine — FastAPI Application

Production-grade API for clinical drug interaction checking.

Endpoints:
  POST /api/v1/drug-safety/check     — Main drug safety analysis
  POST /api/v1/clinical-notes/parse  — Parse free-text clinical notes
  GET  /health                       — Health check
  GET  /api/v1/system-info           — System configuration

Features:
- Strict input validation via Pydantic
- Response adapter for frontend compatibility
- Comprehensive error handling
- CORS middleware for frontend integration
- Clinical notes parsing (LLM + heuristic fallback)
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from models import DrugSafetyRequest, DrugSafetyResponse, RiskBreakdown, RiskLevel, SourceType
from engine import analyze_drug_safety
from cache import interaction_cache
from safety_rules import fallback_db
from llm_interface import llm
from response_adapter import adapt_response_for_frontend
from clinical_notes import (
    ClinicalNoteRequest,
    parse_clinical_note,
)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print("=" * 60)
    print("Clinical Drug Safety Engine -- Starting")
    print("=" * 60)
    if llm.is_available:
        info = llm.model_info
        print(f"  LLM Status  : Available via {info.get('provider', 'Groq')}")
        print(f"  Model       : {info.get('model', 'unknown')}")
        print(f"  Response    : ~1-5 seconds per request")
    else:
        print(f"  LLM Status  : Not available -- {llm.load_error}")
        print(f"  Mode        : Fallback-only (rule-based)")
    print(f"  Fallback DB : {fallback_db.interaction_count} interactions loaded")
    print(f"  Cache TTL   : 3600 seconds")
    print(f"  Frontend    : Vite dev server (proxy mode)")
    print("=" * 60)

    yield

    # Shutdown
    interaction_cache.clear()
    print("Clinical Drug Safety Engine -- Shut down")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Clinical Drug Safety Engine",
    description=(
        "Production-grade API for checking drug-drug interactions, "
        "allergy alerts, and contraindications. Uses Llama 3.3 70B via Groq "
        "with deterministic fallback system."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:5174",    # Vite alternate port
        "http://localhost:3000",    # Alternative dev server
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
        "*",                        # Allow all in development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc: ValidationError):
    """Handle Pydantic validation errors with clear messages."""
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "detail": "Input validation failed. Please check your request.",
            "validation_errors": errors,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions consistently."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """
    Catch-all handler for unexpected errors.
    Returns a safe response rather than crashing.
    """
    print(f"CRITICAL ERROR: Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. The safety team has been notified.",
            "safe_to_prescribe": False,
            "requires_doctor_review": True,
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/api/v1/drug-safety/check",
    summary="Check Drug Safety",
    description=(
        "Analyze proposed medicines for drug interactions, allergy alerts, "
        "and contraindications based on patient history. "
        "Returns frontend-compatible response format."
    ),
)
async def check_drug_safety(request: DrugSafetyRequest):
    """
    Main drug safety analysis endpoint.

    Accepts proposed medicines and patient history, returns comprehensive
    safety analysis including interactions, allergy alerts, contraindications,
    and risk scoring.

    Response is adapted to match the frontend's expected schema.
    """
    try:
        response = analyze_drug_safety(request)
        # Transform to frontend-compatible format
        return adapt_response_for_frontend(response)
    except ValidationError:
        # Re-raise validation errors for the validation handler
        raise
    except Exception as e:
        # If anything goes wrong, return a safe fallback response
        print(f"ERROR in drug safety check: {e}")
        return {
            "overall_risk": "HIGH",
            "patient_risk_score": 75,
            "safe_to_prescribe": False,
            "requires_doctor_review": True,
            "interactions": [],
            "allergies": [],
            "contraindications": [],
            "risk_breakdown": {
                "interaction_risk": 50,
                "allergy_risk": 50,
                "contraindication_risk": 50,
            },
            "warnings": [{
                "category": "special",
                "message": "System error occurred. Manual review is required for safety.",
            }],
            "system_info": {
                "source": "Fallback",
                "cache_hit": False,
                "processing_time_ms": 0,
            },
        }


@app.post(
    "/api/v1/clinical-notes/parse",
    summary="Parse Clinical Note",
    description=(
        "Parse a free-text clinical note to extract structured medical entities "
        "(medicines, conditions, allergies, demographics). Uses LLM when available, "
        "falls back to heuristic parsing."
    ),
)
async def parse_clinical_note_endpoint(request: ClinicalNoteRequest):
    """
    Clinical note parsing endpoint.

    Extracts structured medical entities from free-text clinical notes.
    Used by the frontend's ClinicalChat component for natural language input.
    """
    try:
        result = parse_clinical_note(request.note)
        return result.model_dump()
    except Exception as e:
        print(f"ERROR in clinical note parsing: {e}")
        return {
            "medicines": [],
            "current_medications": [],
            "conditions": [],
            "allergies": [],
            "age": None,
            "weight": None,
            "question": request.note.strip(),
            "source": "Heuristic",
        }


@app.get(
    "/health",
    summary="Health Check",
    description="Returns system health status and component availability.",
)
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "components": {
            "api": "up",
            "llm": "available" if llm.is_available else f"unavailable ({llm.load_error})",
            "fallback_db": f"{fallback_db.interaction_count} interactions",
            "cache": f"{interaction_cache.size} entries",
            "clinical_notes_parser": "available",
        },
        "mode": "llm+fallback" if llm.is_available else "fallback-only",
        "llm_load_error": llm.load_error,
    }


@app.get(
    "/api/v1/system-info",
    summary="System Information",
    description="Returns detailed system configuration and capabilities.",
)
async def system_info():
    """Detailed system info for debugging and monitoring."""
    return {
        "engine": "Clinical Drug Safety Engine",
        "version": "1.0.0",
        "llm": {
            "provider": "Groq (cloud)",
            "model": llm.model_info.get("model", "not loaded") if llm.is_available else "not loaded",
            "available": llm.is_available,
            "error": llm.load_error,
            "config": llm.model_info,
        },
        "fallback": {
            "interactions_count": fallback_db.interaction_count,
            "status": "loaded",
        },
        "cache": {
            "type": "in-memory",
            "ttl_seconds": 3600,
            "current_entries": interaction_cache.size,
        },
        "endpoints": {
            "drug_safety_check": "POST /api/v1/drug-safety/check",
            "clinical_notes_parse": "POST /api/v1/clinical-notes/parse",
            "health": "GET /health",
            "system_info": "GET /api/v1/system-info",
        },
        "safety_features": [
            "Input validation with Pydantic models",
            "LLM output treated as untrusted input",
            "Hallucination detection and filtering",
            "Deterministic allergy cross-matching (22 drug classes)",
            "Condition-based contraindication checks (13 conditions)",
            "Fuzzy drug name matching (Levenshtein distance ≤ 2)",
            "Rule-based fallback with 20+ real interactions",
            "Three-tier safety: LLM → Fallback → Safe minimum response",
            "Thread-safe caching with deterministic keys",
            "Clinical note NLP parsing with fallback",
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
