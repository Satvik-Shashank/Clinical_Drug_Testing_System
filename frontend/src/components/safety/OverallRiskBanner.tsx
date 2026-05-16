import type { SafetyCheckResponse } from "@/lib/safety-types";
import { RiskMeter } from "./RiskMeter";
import { AnimatedNumber } from "./AnimatedNumber";
import { CheckCircle2, AlertOctagon, Stethoscope, Activity } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface Props {
  data: SafetyCheckResponse;
}

const RISK_CONFIG = {
  HIGH: {
    bg: "bg-danger",
    fg: "text-danger-foreground",
    soft: "bg-danger-soft",
    label: "HIGH RISK",
  },
  MEDIUM: {
    bg: "bg-warning",
    fg: "text-warning-foreground",
    soft: "bg-warning-soft",
    label: "MEDIUM RISK",
  },
  LOW: {
    bg: "bg-success",
    fg: "text-success-foreground",
    soft: "bg-success-soft",
    label: "LOW RISK",
  },
};

export function OverallRiskBanner({ data }: Props) {
  const cfg = RISK_CONFIG[data.overall_risk] ?? RISK_CONFIG.MEDIUM;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8, scale: 0.99 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "overflow-hidden rounded-lg border-2 shadow-clinical-lg",
        data.overall_risk === "HIGH" && "border-danger/50",
        data.overall_risk === "MEDIUM" && "border-warning/60",
        data.overall_risk === "LOW" && "border-success/50",
      )}
    >
      {/* Top bar */}
      <div className={cn("flex items-center gap-3 px-5 py-3", cfg.bg, cfg.fg)}>
        <AlertOctagon className="h-5 w-5" strokeWidth={2.5} />
        <span className="text-sm font-bold uppercase tracking-widest">
          {cfg.label}
        </span>
        <span className="ml-auto text-xs font-semibold uppercase tracking-wider opacity-90">
          Clinical Decision Support
        </span>
      </div>

      <div className={cn("grid grid-cols-1 gap-4 p-5 md:grid-cols-4", cfg.soft)}>
        {/* Risk score */}
        <div className="md:col-span-2 rounded-md border border-border bg-card p-4">
          <div className="mb-2 flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Patient Risk Score
            </span>
          </div>
          <div className="mb-2 flex items-baseline gap-2">
            <AnimatedNumber
              value={Math.round(data.patient_risk_score)}
              className="text-4xl font-bold tabular-nums text-foreground"
            />
            <span className="text-sm font-semibold text-muted-foreground">/ 100</span>
          </div>
          <RiskMeter
            value={data.patient_risk_score}
            size="md"
            showValue={false}
          />
        </div>

        {/* Safe to prescribe */}
        <StatusTile
          icon={
            data.safe_to_prescribe ? (
              <CheckCircle2 className="h-5 w-5" />
            ) : (
              <AlertOctagon className="h-5 w-5" />
            )
          }
          label="Safe to Prescribe"
          value={data.safe_to_prescribe ? "YES" : "NO"}
          tone={data.safe_to_prescribe ? "success" : "danger"}
        />

        {/* Doctor review */}
        <StatusTile
          icon={<Stethoscope className="h-5 w-5" />}
          label="Doctor Review"
          value={data.requires_doctor_review ? "REQUIRED" : "NOT REQUIRED"}
          tone={data.requires_doctor_review ? "warning" : "success"}
        />
      </div>
    </motion.div>
  );
}

interface TileProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "success" | "warning" | "danger";
}

function StatusTile({ icon, label, value, tone }: TileProps) {
  const map = {
    success: { ring: "border-success/40", chip: "bg-success text-success-foreground" },
    warning: { ring: "border-warning/50", chip: "bg-warning text-warning-foreground" },
    danger: { ring: "border-danger/50", chip: "bg-danger text-danger-foreground" },
  } as const;
  const m = map[tone];
  return (
    <div className={cn("rounded-md border-2 bg-card p-4", m.ring)}>
      <div className="mb-2 flex items-center gap-2 text-muted-foreground">
        <span className={cn("flex h-7 w-7 items-center justify-center rounded-md", m.chip)}>
          {icon}
        </span>
        <span className="text-xs font-bold uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className="text-lg font-bold tracking-tight text-foreground">
        {value}
      </div>
    </div>
  );
}
