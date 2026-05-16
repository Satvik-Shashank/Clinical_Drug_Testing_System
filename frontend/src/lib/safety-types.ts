// Domain types for the Clinical Drug Safety Engine.

export type Severity = "HIGH" | "MEDIUM" | "LOW";
export type RiskLevel = "HIGH" | "MEDIUM" | "LOW";

export interface PatientHistory {
  current_medications: string[];
  known_allergies: string[];
  conditions: string[];
  age: number;
  weight: number;
}

export interface SafetyCheckRequest {
  medicines: string[];
  patient_history: PatientHistory;
}

export interface DrugInteraction {
  drug_a: string;
  drug_b: string;
  severity: Severity;
  mechanism: string;
  recommendation: string;
}

export interface AllergyAlert {
  drug: string;
  allergen: string;
  reason: string;
  severity: Severity;
}

export interface Contraindication {
  drug: string;
  condition: string;
  reasoning: string;
  severity?: Severity;
}

export interface Warning {
  category: "geriatric" | "weight" | "special" | string;
  drug?: string;
  message: string;
}

export interface RiskBreakdown {
  interaction_risk: number; // 0-100
  allergy_risk: number;
  contraindication_risk: number;
}

export interface SystemInfo {
  source: "LLM" | "Fallback" | string;
  cache_hit: boolean;
  processing_time_ms: number;
}

export interface SafetyCheckResponse {
  overall_risk: RiskLevel;
  patient_risk_score: number; // 0-100
  safe_to_prescribe: boolean;
  requires_doctor_review: boolean;
  interactions: DrugInteraction[];
  allergies: AllergyAlert[];
  contraindications: Contraindication[];
  risk_breakdown: RiskBreakdown;
  warnings: Warning[];
  system_info: SystemInfo;
}

export interface HistoryEntry {
  id: string;
  timestamp: number;
  request: SafetyCheckRequest;
  response: SafetyCheckResponse;
}
