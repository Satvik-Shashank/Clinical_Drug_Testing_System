import { useState, type FormEvent } from "react";
import type { SafetyCheckRequest } from "@/lib/safety-types";
import { TagInput } from "./TagInput";
import { ClinicalCard } from "./ClinicalCard";
import { Pill, ShieldCheck, ClipboardList, User2, ActivitySquare, Loader2, RotateCcw } from "lucide-react";

interface Props {
  loading: boolean;
  onSubmit: (req: SafetyCheckRequest) => void;
  onReset: () => void;
}

const MED_SUGGESTIONS = ["aspirin", "ibuprofen", "warfarin", "metformin", "lisinopril", "atorvastatin"];
const ALLERGY_SUGGESTIONS = ["penicillin", "sulfa", "aspirin", "latex", "iodine"];
const CONDITION_SUGGESTIONS = ["hypertension", "diabetes type 2", "asthma", "CKD", "pregnancy"];

export function InputPanel({ loading, onSubmit, onReset }: Props) {
  const [medicines, setMedicines] = useState<string[]>([]);
  const [currentMeds, setCurrentMeds] = useState<string[]>([]);
  const [allergies, setAllergies] = useState<string[]>([]);
  const [conditions, setConditions] = useState<string[]>([]);
  const [age, setAge] = useState<string>("");
  const [weight, setWeight] = useState<string>("");

  const canSubmit = medicines.length > 0 && age !== "" && weight !== "" && !loading;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      medicines,
      patient_history: {
        current_medications: currentMeds,
        known_allergies: allergies,
        conditions,
        age: Number(age) || 0,
        weight: Number(weight) || 0,
      },
    });
  }

  function handleReset() {
    setMedicines([]);
    setCurrentMeds([]);
    setAllergies([]);
    setConditions([]);
    setAge("");
    setWeight("");
    onReset();
  }

  return (
    <ClinicalCard
      title="Patient & Medication Input"
      subtitle="All fields below feed the safety engine"
      icon={<ClipboardList className="h-4 w-4" strokeWidth={2.5} />}
    >
      <form onSubmit={handleSubmit} className="space-y-5">
        <TagInput
          label="Medicines to evaluate"
          value={medicines}
          onChange={setMedicines}
          placeholder="e.g. aspirin, ibuprofen"
          helperText="Press Enter or comma to add. Required."
          suggestions={MED_SUGGESTIONS}
        />

        <div className="h-px bg-border" />

        <TagInput
          label="Current medications"
          value={currentMeds}
          onChange={setCurrentMeds}
          placeholder="Drugs the patient is already taking"
          suggestions={MED_SUGGESTIONS}
        />

        <TagInput
          label="Known allergies"
          value={allergies}
          onChange={setAllergies}
          placeholder="e.g. penicillin"
          suggestions={ALLERGY_SUGGESTIONS}
        />

        <TagInput
          label="Conditions"
          value={conditions}
          onChange={setConditions}
          placeholder="e.g. hypertension, CKD"
          suggestions={CONDITION_SUGGESTIONS}
        />

        <div className="h-px bg-border" />

        <div className="grid grid-cols-2 gap-4">
          <NumberField
            label="Age (years)"
            value={age}
            onChange={setAge}
            icon={<User2 className="h-3.5 w-3.5" />}
            min={0}
            max={120}
          />
          <NumberField
            label="Weight (kg)"
            value={weight}
            onChange={setWeight}
            icon={<ActivitySquare className="h-3.5 w-3.5" />}
            min={0}
            max={400}
            step={0.1}
          />
        </div>

        <div className="flex flex-col gap-2 pt-2 sm:flex-row">
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex flex-1 items-center justify-center gap-2 rounded-md bg-primary px-4 py-3 text-sm font-bold uppercase tracking-wide text-primary-foreground shadow-clinical transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Analyzing…
              </>
            ) : (
              <>
                <ShieldCheck className="h-4 w-4" strokeWidth={2.5} />
                Run Safety Check
              </>
            )}
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center justify-center gap-2 rounded-md border border-input bg-card px-4 py-3 text-sm font-semibold text-foreground transition-colors hover:bg-muted"
          >
            <RotateCcw className="h-4 w-4" />
            Reset
          </button>
        </div>

        {medicines.length === 0 && (
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Pill className="h-3 w-3" />
            Add at least one medicine to evaluate, plus age and weight.
          </p>
        )}
      </form>
    </ClinicalCard>
  );
}

interface NumberFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  icon?: React.ReactNode;
  min?: number;
  max?: number;
  step?: number;
}

function NumberField({ label, value, onChange, icon, min, max, step }: NumberFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-foreground">
        {icon}
        {label}
      </label>
      <input
        type="number"
        inputMode="decimal"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        min={min}
        max={max}
        step={step}
        className="block w-full rounded-md border border-input bg-surface px-3 py-2.5 text-sm font-medium tabular-nums outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
      />
    </div>
  );
}
