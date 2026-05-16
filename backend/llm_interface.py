"""
Clinical Drug Safety Engine — LLM Interface (Groq API)

Isolated layer for communicating with Llama 3.3 70B via Groq's cloud API.
All LLM interaction is contained here — the rest of the system treats
this as an opaque service that may fail at any time.

Why Groq:
- Free tier: 30 req/min, 14,400 req/day (more than enough)
- Speed: 1–3 seconds per request (vs 90–150s for local CPU inference)
- Model: Llama 3.3 70B — more capable than BioMistral-7B for drug interaction
- Zero local compute: no GPU, no RAM pressure, no compilation

The system is designed so that if Groq fails (network, rate limit, key issue),
it falls back immediately to the deterministic rule-based system.
LLM is the PRIMARY source; fallback is the safety net — not the default.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL      = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT    = float(os.getenv("GROQ_TIMEOUT_SECONDS", "30.0"))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.1"))
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "2"))


# ---------------------------------------------------------------------------
# System Prompt Loading
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Load the clinical pharmacology system prompt."""
    from pathlib import Path
    prompt_path = (
        Path(os.path.dirname(os.path.abspath(__file__)))
        / "prompts"
        / "system_prompt.txt"
    )
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "You are a clinical pharmacology expert. "
            "Respond ONLY with valid JSON containing drug interactions. "
            'Format: {"interactions": [{"drug_a": "", "drug_b": "", '
            '"severity": "high|medium|low", "mechanism": "", '
            '"clinical_recommendation": "", "source_confidence": "high|medium|low"}]}'
        )


SYSTEM_PROMPT = _load_system_prompt()


# ---------------------------------------------------------------------------
# LLM Interface — Groq API
# ---------------------------------------------------------------------------

class LLMInterface:
    """
    Interface for Llama 3.3 70B via Groq's cloud API.

    Handles:
    - API key validation at startup
    - Prompt construction for drug interaction analysis
    - Inference with timeout and retry logic
    - Raw output extraction (validation is done in validation.py)

    The LLM is the PRIMARY source. If it fails (network down, rate limit,
    invalid API key), the engine falls back to the rule-based system.
    """

    def __init__(self) -> None:
        self._client = None
        self._available = False
        self._load_error: Optional[str] = None
        self._model_info: dict = {}
        self._init_client()

    def _init_client(self) -> None:
        """
        Initialise the Groq client and validate the API key.
        Fails gracefully — sets _available = False on any error.
        """
        if not GROQ_API_KEY:
            self._load_error = (
                "GROQ_API_KEY is not set. "
                "Add it to your .env file: GROQ_API_KEY=gsk_..."
            )
            self._available = False
            print(f"INFO: LLM not available — {self._load_error}")
            print("INFO: System will operate in fallback-only mode")
            return

        try:
            from groq import Groq

            self._client = Groq(
                api_key=GROQ_API_KEY,
                timeout=GROQ_TIMEOUT,
                max_retries=0,  # We handle retries ourselves
            )

            # Lightweight connectivity check — list available models
            # This validates the API key without using quota
            self._client.models.list()

            self._available = True
            self._model_info = {
                "provider": "Groq",
                "model": GROQ_MODEL,
                "temperature": GROQ_TEMPERATURE,
                "max_tokens": GROQ_MAX_TOKENS,
                "timeout_seconds": GROQ_TIMEOUT,
            }
            print(f"INFO: [OK] Groq API connected -- model: {GROQ_MODEL}")
            print(f"INFO:   Expected response time: 1-5 seconds")

        except ImportError:
            self._load_error = (
                "groq package is not installed. Run: pip install groq"
            )
            self._available = False
            print(f"INFO: LLM not available — {self._load_error}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            err_str = str(e)
            # Give a clear message for the most common errors
            if "401" in err_str or "authentication" in err_str.lower() or "api_key" in err_str.lower():
                self._load_error = "Invalid GROQ_API_KEY. Check your key at console.groq.com"
            elif "connection" in err_str.lower() or "network" in err_str.lower():
                self._load_error = "Cannot reach Groq API -- check internet connection"
            else:
                self._load_error = f"Groq init failed: {type(e).__name__}: {e}"

            self._available = False
            print(f"WARNING: LLM not available -- {self._load_error}")

    @property
    def is_available(self) -> bool:
        """Whether the Groq client is initialised and the API key is valid."""
        return self._available

    @property
    def load_error(self) -> Optional[str]:
        """Error message if init failed, None if successful."""
        return self._load_error

    @property
    def model_info(self) -> dict:
        """Model metadata for the /api/v1/system-info endpoint."""
        return self._model_info.copy()

    def _build_user_prompt(
        self,
        all_drugs: list[str],
        new_medicines: list[str],
        current_medications: list[str],
    ) -> str:
        """
        Build the user prompt for drug interaction analysis.

        Concise and structured — Llama 3.3 70B handles this format well.
        """
        new_str     = ", ".join(new_medicines)      if new_medicines      else "none"
        current_str = ", ".join(current_medications) if current_medications else "none"
        all_str     = ", ".join(all_drugs)

        return (
            f"Analyze these drugs for clinically significant interactions.\n\n"
            f"NEW MEDICINES (proposed): {new_str}\n"
            f"CURRENT MEDICATIONS (patient already takes): {current_str}\n"
            f"ALL DRUGS TO CHECK: {all_str}\n\n"
            f"Check interactions:\n"
            f"1. Each new medicine vs every other new medicine\n"
            f"2. Each new medicine vs every current medication\n\n"
            f"STRICT RULES:\n"
            f"- Only use drug names from the lists above. NEVER invent drug names.\n"
            f"- Only report interactions you are clinically confident about.\n"
            f'- If no interactions exist, return: {{"interactions": []}}\n'
            f"- Respond with ONLY the JSON object. No explanation, no markdown.\n\n"
            f"JSON:"
        )

    def analyze_interactions(
        self,
        all_drugs: list[str],
        new_medicines: list[str],
        current_medications: list[str],
    ) -> tuple[Optional[str], float]:
        """
        Call Groq API to analyze drug interactions.

        Args:
            all_drugs:           Complete list of all drugs to check
            new_medicines:       Proposed new medicines
            current_medications: Patient's current medications

        Returns:
            tuple of (raw_json_string or None, inference_time_ms)
            Returns (None, 0.0) if client is unavailable.
        """
        if not self._available or self._client is None:
            return None, 0.0

        user_prompt = self._build_user_prompt(
            all_drugs, new_medicines, current_medications
        )

        print(
            f"INFO: Groq [{GROQ_MODEL}] analyzing "
            f"{len(all_drugs)} drugs ({len(new_medicines)} new, "
            f"{len(current_medications)} current) ..."
        )

        last_error: Optional[str] = None

        for attempt in range(1, GROQ_MAX_RETRIES + 2):  # +2 = retries + first try
            start_time = time.time()
            try:
                response = self._client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                    temperature=GROQ_TEMPERATURE,
                    max_tokens=GROQ_MAX_TOKENS,
                    # Ask Groq to return JSON — enables guided decoding on their side
                    response_format={"type": "json_object"},
                )

                elapsed_ms = (time.time() - start_time) * 1000

                content = response.choices[0].message.content
                if content:
                    print(
                        f"INFO: [OK] Groq responded in {elapsed_ms:.0f}ms "
                        f"(attempt {attempt})"
                    )
                    return content, elapsed_ms
                else:
                    last_error = "Empty response content from Groq"

            except Exception as e:
                elapsed_ms = (time.time() - start_time) * 1000
                err_str = str(e)

                # Classify the error
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    last_error = "Groq rate limit hit — falling back to rule DB"
                    print(f"WARNING: {last_error}")
                    break  # No point retrying a rate limit immediately

                elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                    last_error = f"Groq request timed out after {GROQ_TIMEOUT}s"
                    print(f"WARNING: {last_error} (attempt {attempt})")

                elif "401" in err_str or "authentication" in err_str.lower():
                    last_error = "Groq authentication failed — check GROQ_API_KEY"
                    print(f"ERROR: {last_error}")
                    # Disable the client so future requests skip immediately
                    self._available = False
                    self._load_error = last_error
                    return None, elapsed_ms

                else:
                    last_error = f"Groq API error: {type(e).__name__}: {e}"
                    print(f"ERROR: {last_error} (attempt {attempt})")

                if attempt <= GROQ_MAX_RETRIES:
                    wait = 1.5 * attempt  # 1.5s, 3.0s backoff
                    print(f"INFO: Retrying in {wait:.1f}s ...")
                    time.sleep(wait)

        print(f"INFO: Groq failed after {GROQ_MAX_RETRIES + 1} attempt(s): {last_error}")
        print("INFO: Activating fallback rule-based system")
        return None, 0.0


# ---------------------------------------------------------------------------
# Module-level singleton — initialised once at startup
# ---------------------------------------------------------------------------

llm = LLMInterface()
