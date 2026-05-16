import type { RiskBreakdown } from "@/lib/safety-types";
import { RiskMeter } from "./RiskMeter";

interface Props {
  data: RiskBreakdown;
}

const ROWS: Array<{ key: keyof RiskBreakdown; label: string; hint: string }> = [
  {
    key: "interaction_risk",
    label: "Drug Interaction Risk",
    hint: "Pharmacodynamic & pharmacokinetic interactions",
  },
  {
    key: "allergy_risk",
    label: "Allergy Risk",
    hint: "Known allergens & cross-reactivity",
  },
  {
    key: "contraindication_risk",
    label: "Contraindication Risk",
    hint: "Disease-state & condition conflicts",
  },
];

export function RiskBreakdownChart({ data }: Props) {
  return (
    <div className="space-y-5">
      {ROWS.map((r) => {
        const v = data[r.key] ?? 0;
        return (
          <div key={r.key}>
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-foreground">{r.label}</p>
                <p className="text-[11px] text-muted-foreground">{r.hint}</p>
              </div>
              <span className="text-base font-bold tabular-nums text-foreground">
                {Math.round(v)}
                <span className="ml-0.5 text-[10px] font-semibold text-muted-foreground">
                  /100
                </span>
              </span>
            </div>
            <RiskMeter value={v} size="lg" showValue={false} />
          </div>
        );
      })}
    </div>
  );
}
