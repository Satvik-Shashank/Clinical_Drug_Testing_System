import type { SafetyCheckRequest, SafetyCheckResponse, HistoryEntry } from "@/lib/safety-types";
import { motion } from "framer-motion";
import { ClinicalCard } from "./ClinicalCard";
import { OverallRiskBanner } from "./OverallRiskBanner";
import { SeverityBadge } from "./SeverityBadge";
import { RiskBreakdownChart } from "./RiskBreakdownChart";
import { AlertBanner } from "./AlertBanner";
import { ExplainSection } from "./ExplainSection";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Cpu,
  Download,
  FileText,
  ShieldAlert,
  Stethoscope,
} from "lucide-react";
import { exportSafetyReportPdf } from "@/lib/pdf-export";

interface Props {
  loading: boolean;
  data: SafetyCheckResponse | null;
  request: SafetyCheckRequest | null;
  entry: HistoryEntry | null;
}

export function ResultsPanel({ loading, data, request, entry }: Props) {
  if (loading) return <LoadingState />;
  if (!data || !request) return <EmptyState />;

  const usingFallback = data.system_info.source !== "LLM";

  return (
    <motion.div
      className="space-y-5"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
    >
      {usingFallback && (
        <AlertBanner
          tone="warning"
          title="Fallback engine active — Doctor review required"
          description="The primary safety engine could not be reached or returned an empty result. The system has failed safe and produced a conservative assessment. Verify all results manually."
        />
      )}

      <OverallRiskBanner data={data} />

      {/* Drug interactions */}
      <ClinicalCard
        title="Drug Interactions"
        subtitle="Pairwise pharmacological conflicts"
        icon={<AlertTriangle className="h-4 w-4" strokeWidth={2.5} />}
        count={data.interactions.length}
        countTone={data.interactions.length > 0 ? "warning" : "success"}
        tone={data.interactions.some((i) => i.severity === "HIGH") ? "danger" : "default"}
      >
        {data.interactions.length === 0 ? (
          <EmptyRow text="No drug-drug interactions detected." tone="success" />
        ) : (
          <ul className="space-y-3">
            {data.interactions.map((it, idx) => (
              <li
                key={idx}
                className="rounded-md border border-border bg-surface-elevated p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-bold tracking-tight text-foreground">
                    <span className="rounded bg-accent px-2 py-0.5 text-accent-foreground">
                      {it.drug_a}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="rounded bg-accent px-2 py-0.5 text-accent-foreground">
                      {it.drug_b}
                    </span>
                  </div>
                  <SeverityBadge severity={it.severity} />
                </div>
                <dl className="mt-3 space-y-2 text-sm">
                  <Field label="Mechanism" value={it.mechanism} />
                  <Field
                    label="Recommendation"
                    value={it.recommendation}
                    valueClass="font-semibold text-foreground"
                  />
                </dl>
                <ExplainSection>
                  This interaction was flagged because {it.drug_a.toLowerCase()} and{" "}
                  {it.drug_b.toLowerCase()} share an overlapping pharmacologic pathway:{" "}
                  {it.mechanism.toLowerCase()}. Severity{" "}
                  <strong>{it.severity}</strong> indicates the magnitude of expected
                  clinical impact. Always cross-check with current prescribing information.
                </ExplainSection>
              </li>
            ))}
          </ul>
        )}
      </ClinicalCard>

      {/* Allergies */}
      <ClinicalCard
        title="Allergy Alerts"
        subtitle="Known allergen matches & cross-reactivity"
        icon={<ShieldAlert className="h-4 w-4" strokeWidth={2.5} />}
        count={data.allergies.length}
        countTone={data.allergies.length > 0 ? "danger" : "success"}
        tone={data.allergies.length > 0 ? "danger" : "default"}
      >
        {data.allergies.length === 0 ? (
          <EmptyRow text="No allergy conflicts detected." tone="success" />
        ) : (
          <ul className="space-y-3">
            {data.allergies.map((a, idx) => (
              <li
                key={idx}
                className="rounded-md border-2 border-danger/40 bg-danger-soft p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                    <AlertOctagon className="h-4 w-4 text-danger" strokeWidth={2.5} />
                    <span>{a.drug}</span>
                    <span className="text-muted-foreground">matches allergen</span>
                    <span className="rounded bg-card px-2 py-0.5 text-danger">
                      {a.allergen}
                    </span>
                  </div>
                  <SeverityBadge severity={a.severity} />
                </div>
                <p className="mt-2 text-sm leading-relaxed text-foreground">
                  {a.reason}
                </p>
              </li>
            ))}
          </ul>
        )}
      </ClinicalCard>

      {/* Contraindications */}
      <ClinicalCard
        title="Contraindications"
        subtitle="Disease-state & condition conflicts"
        icon={<Stethoscope className="h-4 w-4" strokeWidth={2.5} />}
        count={data.contraindications.length}
        countTone={data.contraindications.length > 0 ? "warning" : "success"}
      >
        {data.contraindications.length === 0 ? (
          <EmptyRow text="No contraindications identified." tone="success" />
        ) : (
          <ul className="space-y-3">
            {data.contraindications.map((c, idx) => (
              <li
                key={idx}
                className="rounded-md border border-border bg-surface-elevated p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-bold text-foreground">
                    <span className="rounded bg-accent px-2 py-0.5 text-accent-foreground">
                      {c.drug}
                    </span>
                    <span className="mx-2 text-muted-foreground">vs</span>
                    <span className="rounded bg-warning-soft px-2 py-0.5 text-foreground">
                      {c.condition}
                    </span>
                  </p>
                  {c.severity ? <SeverityBadge severity={c.severity} /> : null}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {c.reasoning}
                </p>
              </li>
            ))}
          </ul>
        )}
      </ClinicalCard>

      {/* Risk breakdown + Warnings — side by side on desktop */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <ClinicalCard
          className="lg:col-span-3"
          title="Risk Breakdown"
          subtitle="Component-level contribution to overall score"
          icon={<BarChart3 className="h-4 w-4" strokeWidth={2.5} />}
        >
          <RiskBreakdownChart data={data.risk_breakdown} />
        </ClinicalCard>

        <ClinicalCard
          className="lg:col-span-2"
          title="Warnings"
          subtitle="Geriatric, weight-based & special notes"
          icon={<AlertTriangle className="h-4 w-4" strokeWidth={2.5} />}
          count={data.warnings.length}
          countTone={data.warnings.length > 0 ? "warning" : "success"}
        >
          {data.warnings.length === 0 ? (
            <EmptyRow text="No additional warnings." tone="success" />
          ) : (
            <ul className="space-y-2">
              {data.warnings.map((w, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-soft p-3"
                >
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning"
                    strokeWidth={2.5}
                  />
                  <div className="min-w-0">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-warning">
                      {w.category}
                      {w.drug ? ` · ${w.drug}` : ""}
                    </p>
                    <p className="text-sm leading-relaxed text-foreground">
                      {w.message}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </ClinicalCard>
      </div>

      {/* Actions + System info */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SystemInfoStrip data={data} />
        <button
          type="button"
          onClick={() => entry && exportSafetyReportPdf(entry)}
          disabled={!entry}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-primary bg-card px-4 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground disabled:opacity-50"
        >
          <Download className="h-4 w-4" />
          Export PDF Report
        </button>
      </div>
    </motion.div>
  );
}

/* ---------- helpers ---------- */

function Field({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-3">
      <dt className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className={`text-sm leading-relaxed text-muted-foreground ${valueClass ?? ""}`}>
        {value}
      </dd>
    </div>
  );
}

function EmptyRow({ text, tone }: { text: string; tone: "success" | "muted" }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-md border p-3 text-sm font-medium ${
        tone === "success"
          ? "border-success/30 bg-success-soft text-foreground"
          : "border-border bg-muted/30 text-muted-foreground"
      }`}
    >
      <Activity className="h-4 w-4" />
      {text}
    </div>
  );
}

function SystemInfoStrip({ data }: { data: SafetyCheckResponse }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <Cpu className="h-3 w-3" />
        Source:{" "}
        <strong
          className={
            data.system_info.source === "LLM" ? "text-primary" : "text-warning"
          }
        >
          {data.system_info.source}
        </strong>
      </span>
      <span className="inline-flex items-center gap-1.5">
        Cache hit:{" "}
        <strong className="text-foreground">
          {data.system_info.cache_hit ? "true" : "false"}
        </strong>
      </span>
      <span className="inline-flex items-center gap-1.5 tabular-nums">
        Processing time:{" "}
        <strong className="text-foreground">
          {data.system_info.processing_time_ms} ms
        </strong>
      </span>
    </div>
  );
}

function LoadingState() {
  return (
    <ClinicalCard
      title="Analyzing Drug Safety"
      subtitle="Engine is evaluating interactions, allergies & contraindications"
      icon={<Activity className="h-4 w-4 animate-pulse" />}
    >
      <div className="space-y-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
            <div className="h-16 animate-pulse rounded-md bg-muted/60" />
          </div>
        ))}
        <p className="pt-2 text-center text-xs font-medium text-muted-foreground">
          Cross-referencing pharmacologic database…
        </p>
      </div>
    </ClinicalCard>
  );
}

function EmptyState() {
  return (
    <ClinicalCard
      title="Awaiting input"
      subtitle="Results will appear here after a safety check"
      icon={<FileText className="h-4 w-4" />}
    >
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent">
          <Stethoscope className="h-7 w-7 text-primary" strokeWidth={2} />
        </div>
        <div>
          <p className="text-base font-bold text-foreground">
            Ready for clinical review
          </p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            Enter the medicines you intend to prescribe along with the patient's
            history, then run the safety check to view interactions, allergy
            alerts, contraindications, and an overall risk score.
          </p>
        </div>
      </div>
    </ClinicalCard>
  );
}
