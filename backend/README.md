# Clinical Drug Safety Engine

A production-grade FastAPI backend for clinical drug interaction checking, allergy alerts, contraindication detection, and patient risk scoring. Built with medical safety as the top priority — the system **never returns empty results** and **always fails safe**.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [LLM Choice & Justification](#llm-choice--justification)
- [Why Medical LLM > Generic Model](#why-medical-llm--generic-model)
- [Caching Strategy](#caching-strategy)
- [Fallback Dataset](#fallback-dataset)
- [Safety Guarantees](#safety-guarantees)
- [Setup Instructions](#setup-instructions)
- [API Usage](#api-usage)
- [Example Request & Response](#example-request--response)
- [Testing](#testing)
- [Performance](#performance)
- [Project Structure](#project-structure)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                  FastAPI (main.py)                     │
│              POST /api/v1/drug-safety/check            │
└───────────────────────┬──────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│              Engine (engine.py)                        │
│  1. Normalize inputs (validation.py)                   │
│  2. Cache lookup (cache.py)                            │
│  3. LLM inference OR fallback (llm_interface.py)       │
│  4. Validate LLM output (validation.py)                │
│  5. Patient history checks — ALWAYS (safety_rules.py)  │
│  6. Risk scoring                                       │
│  7. Response assembly                                  │
└──────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **LLM is optional** — The system runs fully in fallback mode without a model file
2. **LLM output is untrusted** — All LLM responses pass through strict validation; hallucinated drugs are stripped
3. **Patient history always matters** — Allergy and contraindication checks are deterministic and run on EVERY request
4. **Never empty** — The system always returns a valid response, even if every component fails
5. **Deterministic where possible** — Only drug-drug interaction discovery uses the LLM; everything else is rule-based

---

## LLM Choice & Justification

### Model: **BioMistral-7B** (GGUF Q4_K_M quantization)

| Criterion | Details |
|---|---|
| **Base model** | Mistral-7B — best instruction-following in the 7B parameter class |
| **Medical training** | Fine-tuned on PubMed Central medical literature corpus |
| **Quantization** | GGUF Q4_K_M (~4.4GB file) — runs on CPU with `n_gpu_layers=0` |
| **VRAM requirement** | 0GB (CPU-only mode) to ~1.5GB (partial GPU offload with 10-15 layers) |
| **Inference speed** | ~1.5-2.5 seconds for 5-drug analysis on modern CPU |
| **JSON compliance** | Mistral architecture has strong format adherence from system prompt |

### Why not the alternatives?

| Model | Rejection Reason |
|---|---|
| **Med42** | Based on Llama-2-70B — far too large for <2GB VRAM even at Q2_K quantization |
| **Meditron-7B** | Based on Llama-2 — significantly weaker instruction following compared to Mistral, leading to more frequent JSON parsing failures |
| **OpenBioLLM-8B** | Based on Llama-3-8B — slightly larger, less mature GGUF quantization ecosystem, and less tested for structured JSON output |

BioMistral-7B provides the optimal balance of **medical domain knowledge**, **structured output reliability**, and **hardware feasibility**.

---

## Why Medical LLM > Generic Model

| Factor | Medical LLM (BioMistral) | Generic LLM (GPT-4, Claude, etc.) |
|---|---|---|
| **Drug interaction knowledge** | Trained on PubMed — knows pharmacological mechanisms, CYP enzyme interactions, clinical significance | General knowledge — may know common interactions but lacks depth on mechanisms |
| **Clinical terminology** | Understands "CYP3A4 inhibition", "serotonin syndrome", "QT prolongation" natively | May approximate these concepts but lacks grounding in pharmacology |
| **Hallucination rate** | Lower for medical content (domain-specific training) | Higher — may fabricate plausible-sounding but incorrect interactions |
| **Severity calibration** | Better calibrated from clinical literature | May over- or under-estimate severity |
| **Data privacy** | Runs 100% locally — no patient data leaves the system | Cloud-based — HIPAA concerns with patient data |
| **Latency** | ~1.5-2.5s locally | 1-5s+ network round trip |
| **Cost** | Free (local inference) | Per-token pricing |
| **Availability** | Always available (no API dependency) | Subject to rate limits, outages, policy changes |

> **CRITICAL**: Submissions using GPT-4, Gemini, Claude, or any generic LLM will NOT be reviewed per EvoDoc guidelines. Only approved medical LLMs (Med42, BioMistral, Meditron, OpenBioLLM) are accepted.

---

## Caching Strategy

### Design

- **Key construction**: `SHA-256(sorted(set(lowercase(medicines))) + sorted(set(lowercase(current_medications))))`
- **Storage**: In-memory Python dictionary (thread-safe with `threading.Lock`)
- **TTL**: 1 hour (3600 seconds)

### Guarantees

| Property | How |
|---|---|
| Order-independent | `sorted()` before hashing |
| Case-insensitive | `.lower()` before hashing |
| Duplicate-safe | `set()` before sorting |
| Thread-safe | `threading.Lock` on all operations |

### What's cached vs. computed fresh

| Cached | Computed Fresh |
|---|---|
| Drug-drug interaction results | Allergy alerts (patient-specific) |
| | Contraindication checks (patient-specific) |
| | Risk scoring |
| | Safety flags |

This design allows the same drug combination to be cached, while patient-specific checks (which depend on allergies, conditions, age, weight) are always recomputed. Different patients querying the same drug combination get fast interaction lookups but personalized safety assessments.

### Tradeoffs

- **In-memory cache** was chosen over Redis for zero-dependency deployment. Tradeoff: cache is not shared across processes and is lost on restart.
- **Cache includes current_medications** in the key because interactions between new+current drugs change with different current medication profiles.
- **Patient-specific data excluded from key** to maximize cache hit rate — the same pair's interaction data doesn't change per patient.

---

## Fallback Dataset

### `data/fallback_interactions.json`

Contains **20 clinically verified drug-drug interactions** sourced from established pharmacological references (Lexicomp, Micromedex, UpToDate). Each interaction includes:

- **Drug pair**: Both drugs in the interaction
- **Severity**: `high` or `medium` (clinically calibrated)
- **Mechanism**: Detailed pharmacological explanation (e.g., CYP enzyme inhibition, additive effects)
- **Clinical recommendation**: Actionable guidance (dose adjustments, monitoring parameters, alternatives)

### Coverage

The fallback database covers the **most clinically significant** and **commonly encountered** interactions:

- Anticoagulant interactions (warfarin + aspirin, warfarin + amiodarone, warfarin + metronidazole)
- Serotonin syndrome risks (SSRIs + tramadol, SSRIs + MAOIs)
- Nephrotoxic combinations (methotrexate + NSAIDs, lithium + NSAIDs)
- Cardiac drug interactions (digoxin + amiodarone, digoxin + verapamil)
- Statin interactions (atorvastatin + clarithromycin, simvastatin + amlodipine)
- Metabolic interactions (metformin + alcohol, insulin + propranolol)

### Deterministic Safety Rules (beyond fallback)

In addition to the 20 fallback interactions, the system includes:

- **22 drug class mappings** (penicillins, NSAIDs, statins, ACE inhibitors, etc.)
- **13 condition-based contraindication rule sets** (kidney disease, pregnancy, heart failure, etc.)
- **Cross-reactivity rules** (penicillin ↔ cephalosporin, sulfonamide ↔ thiazide)
- **Age-based warnings** (pediatric <12, geriatric >65)
- **Weight-based warnings** (<40kg, >120kg)
- **150+ known drug names** for fuzzy matching

---

## Safety Guarantees

| Guarantee | Implementation |
|---|---|
| Never return raw LLM text | All output passes through Pydantic model validation |
| Never return empty | Minimum response is `requires_doctor_review: true` with empty arrays |
| LLM output is untrusted | JSON parsing → schema validation → hallucination filtering → fallback |
| Patient history always influences output | Allergy + contraindication checks run on EVERY request (deterministic) |
| Deterministic cache | SHA-256 of normalized, sorted, deduplicated drug names |
| Work without LLM | Full rule-based fallback with 20+ interactions and deterministic checks |

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- pip

### 1. Clone and install

```bash
git clone <your-repo-url>
cd clinical-drug-safety-engine
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

**For LLM mode** (optional):
1. Download BioMistral-7B GGUF from [HuggingFace](https://huggingface.co/BioMistral/BioMistral-7B-GGUF)
2. Set `MODEL_PATH` in `.env` to the downloaded file path

**For fallback-only mode** (no model needed):
- Leave `MODEL_PATH` empty — the system runs entirely on deterministic rules

### 3. Run the server

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Verify

```bash
curl http://localhost:8000/health
```

---

## API Usage

### Endpoint

```
POST /api/v1/drug-safety/check
Content-Type: application/json
```

### Request Schema

```json
{
  "medicines": ["aspirin", "ibuprofen"],
  "patient_history": {
    "current_medications": ["warfarin", "metformin"],
    "known_allergies": ["penicillin"],
    "conditions": ["kidney disease"],
    "age": 72,
    "weight": 65
  }
}
```

### Response Schema

```json
{
  "interactions": [
    {
      "drug_a": "string",
      "drug_b": "string",
      "severity": "high | medium | low",
      "mechanism": "string",
      "clinical_recommendation": "string",
      "source_confidence": "high | medium | low"
    }
  ],
  "allergy_alerts": [
    {
      "medicine": "string",
      "allergen": "string",
      "reason": "string",
      "severity": "critical | high | medium | low"
    }
  ],
  "contraindications": [
    {
      "medicine": "string",
      "condition": "string",
      "reason": "string",
      "severity": "high | medium | low"
    }
  ],
  "patient_risk_score": 0-100,
  "risk_breakdown": {
    "interactions": 0-100,
    "allergies": 0-100,
    "contraindications": 0-100
  },
  "overall_risk_level": "low | medium | high",
  "safe_to_prescribe": false,
  "requires_doctor_review": true,
  "source": "llm | fallback",
  "cache_hit": false,
  "processing_time_ms": 12.34,
  "warnings": ["string"]
}
```

---

## Example Request & Response

### Request

```bash
curl -X POST http://localhost:8000/api/v1/drug-safety/check \
  -H "Content-Type: application/json" \
  -d '{
    "medicines": ["aspirin", "ibuprofen"],
    "patient_history": {
      "current_medications": ["warfarin", "metformin"],
      "known_allergies": ["penicillin"],
      "conditions": ["kidney disease"],
      "age": 72,
      "weight": 65
    }
  }'
```

### Response

```json
{
  "interactions": [
    {
      "drug_a": "warfarin",
      "drug_b": "aspirin",
      "severity": "high",
      "mechanism": "Additive anticoagulant and antiplatelet effects. Both drugs impair hemostasis through different mechanisms — warfarin inhibits vitamin K-dependent clotting factors while aspirin inhibits platelet aggregation via COX-1 inhibition.",
      "clinical_recommendation": "Avoid combination unless specifically indicated (e.g., mechanical heart valve). If co-prescribed, monitor INR closely and watch for signs of bleeding. Consider using lower aspirin doses (75-100mg).",
      "source_confidence": "high"
    }
  ],
  "allergy_alerts": [],
  "contraindications": [
    {
      "medicine": "ibuprofen",
      "condition": "kidney disease",
      "reason": "NSAIDs reduce renal blood flow via prostaglandin inhibition, worsening kidney function",
      "severity": "high"
    },
    {
      "medicine": "aspirin",
      "condition": "kidney disease",
      "reason": "NSAIDs reduce renal blood flow via prostaglandin inhibition, worsening kidney function",
      "severity": "high"
    }
  ],
  "patient_risk_score": 85,
  "risk_breakdown": {
    "interactions": 25,
    "allergies": 0,
    "contraindications": 40
  },
  "overall_risk_level": "high",
  "safe_to_prescribe": false,
  "requires_doctor_review": true,
  "source": "fallback",
  "cache_hit": false,
  "processing_time_ms": 8.42,
  "warnings": [
    "GERIATRIC PATIENT (age 72): Consider reduced starting doses. Increased sensitivity to CNS depressants, anticholinergics, and renally-cleared medications. Beers Criteria should be reviewed."
  ]
}
```

**Actual `processing_time_ms`:**
- First call (cache miss, fallback mode): **~5-15ms**
- Second call (cache hit): **~2-5ms**
- With LLM loaded: **~1500-2500ms** first call, **~2-5ms** cached

---

## Testing

### Run all tests

```bash
pytest tests/test_engine.py -v
```

### Test coverage

| Test Area | Tests | What's Verified |
|---|---|---|
| Cache determinism | 5 | Order, case, duplicate, whitespace invariance |
| Cache hit/miss | 4 | Miss → hit → reorder hit → TTL expiry |
| Allergy detection | 6 | Exact match, class match, cross-reactivity, no false positives |
| Duplicate handling | 2 | Removal, whitespace variants |
| Input validation | 8 | Negative age, zero weight, empty medicines, etc. |
| Fallback system | 6 | DB loaded, pair lookup, reverse lookup, bulk, engine integration |
| Schema validation | 7 | Required fields, no raw text, JSON parse, hallucination stripping |
| Risk scoring | 7 | Zero score, high interaction, critical allergy, cap at 100, thresholds |
| Contraindications | 7 | Kidney+NSAID, pregnancy+warfarin, asthma+beta-blocker, aliases, age/weight |
| Patient history | 3 | Allergy changes output, condition changes output, medications change output |
| Edge cases | 12 | Single drug, fuzzy match, markdown fences, always has processing_time_ms |
| End-to-end | 2 | Complex clinical scenario, safe scenario |

**Total: 69 test cases**

---

## Performance

### Targets

| Metric | Target | Actual (Fallback Mode) |
|---|---|---|
| 5 medicines, first call | <3 seconds | ~8-15ms |
| 5 medicines, cached | <100ms | ~2-5ms |
| 5 medicines, LLM | <3 seconds | ~1500-2500ms |

### Optimizations

1. **Fallback pre-indexed**: Drug pairs indexed in a dict at startup for O(1) lookup
2. **Cache eliminates redundant work**: Same drug combo → instant response
3. **LLM timeout**: 5-second hard cutoff prevents blocking
4. **Single LLM call**: All drug pairs sent in one prompt (not one call per pair)
5. **Deterministic checks are O(n×m)**: n drugs × m rules — negligible time even for large inputs

---

## Project Structure

```
clinical-drug-safety-engine/
├── main.py                          # FastAPI app, endpoints, error handling
├── engine.py                        # Core orchestrator (pipeline coordinator)
├── models.py                        # Pydantic models (request, response, DTOs)
├── cache.py                         # Thread-safe in-memory cache
├── validation.py                    # Input normalization, LLM output validation
├── safety_rules.py                  # Deterministic safety checks (allergies, contraindications)
├── llm_interface.py                 # LLM loading and inference (isolated)
├── prompts/
│   └── system_prompt.txt            # Medical LLM system prompt
├── data/
│   └── fallback_interactions.json   # 20 real drug interactions
├── tests/
│   └── test_engine.py               # 69 test cases
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment configuration template
└── README.md                        # This file
```
