import axios, { AxiosError } from "axios";
import type { SafetyCheckRequest, SafetyCheckResponse } from "./safety-types";

const API_BASE =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE_URL) || "";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

/**
 * Fail-safe response. Per backend spec: NEVER return empty results,
 * ALWAYS fail safe and require doctor review.
 */
function buildFailSafeResponse(
  request: SafetyCheckRequest,
  reason: string,
): SafetyCheckResponse {
  return {
    overall_risk: "HIGH",
    patient_risk_score: 75,
    safe_to_prescribe: false,
    requires_doctor_review: true,
    interactions: [],
    allergies: [],
    contraindications: [],
    risk_breakdown: {
      interaction_risk: 50,
      allergy_risk: 50,
      contraindication_risk: 50,
    },
    warnings: [
      {
        category: "special",
        message:
          "Unable to fully analyze drug safety. Doctor review required before prescribing. " +
          `(${reason})`,
      },
      ...(request.patient_history.age >= 65
        ? [
            {
              category: "geriatric" as const,
              message:
                "Patient is geriatric (≥65). Apply Beers Criteria and consider reduced dosing.",
            },
          ]
        : []),
    ],
    system_info: {
      source: "Fallback",
      cache_hit: false,
      processing_time_ms: 0,
    },
  };
}

export async function runSafetyCheck(
  request: SafetyCheckRequest,
): Promise<SafetyCheckResponse> {
  try {
    const { data } = await client.post<SafetyCheckResponse>(
      "/api/v1/drug-safety/check",
      request,
    );
    if (!data || typeof data !== "object") {
      return buildFailSafeResponse(request, "Empty response from safety engine");
    }
    return data;
  } catch (err) {
    const axErr = err as AxiosError;
    const reason =
      axErr.response?.status != null
        ? `HTTP ${axErr.response.status}`
        : axErr.message || "Network error";
    return buildFailSafeResponse(request, reason);
  }
}
