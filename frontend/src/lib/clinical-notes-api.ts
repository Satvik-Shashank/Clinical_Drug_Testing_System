import axios, { AxiosError } from "axios";
import type { SafetyCheckRequest } from "./safety-types";

const API_BASE =
  (typeof import.meta !== "undefined" && (import.meta as any).env?.VITE_API_BASE_URL) || "";

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

export interface ParsedClinicalNote {
  medicines: string[];
  current_medications: string[];
  conditions: string[];
  allergies: string[];
  age?: number;
  weight?: number;
  /** Free-text clinical question extracted from the note, if any. */
  question?: string;
  /** Source of the parse — "LLM" | "Heuristic" (local fallback). */
  source: "LLM" | "Heuristic";
}

/* ---------------------------------------------------------------- */
/* Local heuristic parser — used as fail-safe when API is offline.   */
/* This is intentionally conservative; the engine still re-validates.*/
/* ---------------------------------------------------------------- */

const COMMON_DRUGS = [
  "aspirin", "ibuprofen", "warfarin", "metformin", "lisinopril", "atorvastatin",
  "amoxicillin", "penicillin", "clopidogrel", "heparin", "naproxen", "paracetamol",
  "acetaminophen", "amlodipine", "omeprazole", "simvastatin", "losartan",
  "ciprofloxacin", "azithromycin", "prednisone", "insulin", "digoxin",
  "furosemide", "metoprolol", "tramadol", "morphine", "codeine", "diazepam",
];

const COMMON_CONDITIONS = [
  "hypertension", "diabetes", "asthma", "ckd", "kidney disease", "liver disease",
  "pregnancy", "heart failure", "copd", "epilepsy", "depression", "anxiety",
  "ulcer", "gerd", "stroke", "arrhythmia", "atrial fibrillation",
];

const COMMON_ALLERGENS = [
  "penicillin", "sulfa", "aspirin", "latex", "iodine", "nsaid", "nsaids",
  "peanut", "shellfish",
];

function uniqLower(arr: string[]): string[] {
  return Array.from(new Set(arr.map((s) => s.trim().toLowerCase()).filter(Boolean)));
}

function findTokens(text: string, vocabulary: string[]): string[] {
  const lower = text.toLowerCase();
  const found: string[] = [];
  for (const term of vocabulary) {
    const re = new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (re.test(lower)) found.push(term);
  }
  return uniqLower(found);
}

function extractAge(text: string): number | undefined {
  const m =
    text.match(/\b(\d{1,3})\s*(?:y\/?o|yo|years?\s*old|year-old)\b/i) ||
    text.match(/\bage[:\s]+(\d{1,3})\b/i);
  if (m) {
    const n = Number(m[1]);
    if (n > 0 && n < 130) return n;
  }
  return undefined;
}

function extractWeight(text: string): number | undefined {
  const m = text.match(/\b(\d{1,3}(?:\.\d+)?)\s*kg\b/i);
  if (m) {
    const n = Number(m[1]);
    if (n > 0 && n < 400) return n;
  }
  return undefined;
}

function localParse(note: string): ParsedClinicalNote {
  const text = note;
  // Heuristic: anything in "current meds: X, Y" or "on X" -> current meds
  // anything in "give/start/prescribe X" -> proposed medicine
  const proposedMatch = text.match(
    /\b(?:give|start|prescribe|add|consider)\s+([a-z][a-z\-\s,]+)/i,
  );
  const onMatch = text.match(/\b(?:on|taking|takes)\s+([a-z][a-z\-\s,]+)/i);

  const allDrugs = findTokens(text, COMMON_DRUGS);
  const proposed = proposedMatch
    ? findTokens(proposedMatch[1], COMMON_DRUGS)
    : [];
  const onMeds = onMatch ? findTokens(onMatch[1], COMMON_DRUGS) : [];

  // Whatever wasn't classified as "on" or "proposed" → treat as proposed by default
  const classified = new Set([...proposed, ...onMeds]);
  const unclassified = allDrugs.filter((d) => !classified.has(d));

  const medicines = uniqLower([
    ...proposed,
    ...(proposed.length === 0 ? unclassified : []),
  ]);
  const current_medications = uniqLower([
    ...onMeds,
    ...(proposed.length > 0 ? unclassified : []),
  ]);

  const conditions = findTokens(text, COMMON_CONDITIONS);
  const allergies = text.match(/\b(?:allergic to|allergy to|allergies?)[:\s]+([a-z,\s]+)/i)
    ? findTokens(text, COMMON_ALLERGENS)
    : [];

  return {
    medicines,
    current_medications,
    conditions,
    allergies,
    age: extractAge(text),
    weight: extractWeight(text),
    question: text.trim(),
    source: "Heuristic",
  };
}

/* ---------------------------------------------------------------- */
/* Public API                                                        */
/* ---------------------------------------------------------------- */

export async function parseClinicalNote(note: string): Promise<ParsedClinicalNote> {
  try {
    const { data } = await client.post<Partial<ParsedClinicalNote>>(
      "/api/v1/clinical-notes/parse",
      { note },
    );
    if (!data || typeof data !== "object") {
      return localParse(note);
    }
    return {
      medicines: uniqLower(data.medicines ?? []),
      current_medications: uniqLower(data.current_medications ?? []),
      conditions: uniqLower(data.conditions ?? []),
      allergies: uniqLower(data.allergies ?? []),
      age: typeof data.age === "number" ? data.age : extractAge(note),
      weight: typeof data.weight === "number" ? data.weight : extractWeight(note),
      question: data.question ?? note.trim(),
      source: "LLM",
    };
  } catch (err) {
    void (err as AxiosError);
    return localParse(note);
  }
}

/** Convert a parsed note → a SafetyCheckRequest the engine can consume. */
export function parsedNoteToSafetyRequest(
  parsed: ParsedClinicalNote,
  defaults?: { age?: number; weight?: number },
): SafetyCheckRequest {
  return {
    medicines: parsed.medicines,
    patient_history: {
      current_medications: parsed.current_medications,
      known_allergies: parsed.allergies,
      conditions: parsed.conditions,
      age: parsed.age ?? defaults?.age ?? 0,
      weight: parsed.weight ?? defaults?.weight ?? 0,
    },
  };
}
