import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  AlertTriangle,
  ShieldCheck,
  ArrowRight,
  Pill,
  HeartPulse,
  Stethoscope,
  Loader2,
  FlaskConical,
  Plus,
  ScanSearch,
  CheckCircle2,
  Activity,
  Brain,
  UserRound,
  ChevronRight,
  Thermometer,
  Info,
  Terminal,
} from "lucide-react";
import { SeverityBadge } from "./SeverityBadge";
import { RiskMeter } from "./RiskMeter";
import { cn } from "@/lib/utils";
import {
  parseClinicalNote,
  parsedNoteToSafetyRequest,
  type ParsedClinicalNote,
} from "@/lib/clinical-notes-api";
import { runSafetyCheck } from "@/lib/safety-api";
import type { SafetyCheckRequest, SafetyCheckResponse } from "@/lib/safety-types";

interface Props {
  onPromoteToCase: (req: SafetyCheckRequest, res: SafetyCheckResponse) => void;
  defaults?: { age?: number; weight?: number };
}

type Phase = "overview" | "boot" | "active";

interface UserMsg {
  id: string;
  role: "user";
  content: string;
}

interface IntakeMsg {
  id: string;
  role: "intake";
  acknowledgment: string;
  symptoms: string[];
  confirmed: boolean;
}

interface AssistantMsg {
  id: string;
  role: "assistant";
  status: "thinking" | "ready" | "error";
  parsed?: ParsedClinicalNote;
  request?: SafetyCheckRequest;
  response?: SafetyCheckResponse;
  reasoning?: string;
  recommendation?: string;
  errorText?: string;
}

type Msg = UserMsg | IntakeMsg | AssistantMsg;

const PATIENT_OVERVIEW = {
  recordId: "#2992",
  patientName: "Akshit Ohri",
  summary:
    "Geriatric patient with CHF and CKD presenting with signs of fluid overload.",
  symptoms: ["Shortness of Breath", "Bilateral Ankle Edema", "Weight gain (2kg)"],
};

const BOOT_LINES = [
  "ESTABLISH SECURE CONNECTION...",
  "AUTHENTICATING CLINICIAN CREDENTIALS...",
  `PATIENT RECORD ${PATIENT_OVERVIEW.recordId} PULLED.`,
  "LOADING CLINICAL REASONING ENGINE...",
];

export function ClinicalChat({ onPromoteToCase, defaults }: Props) {
  const [phase, setPhase] = useState<Phase>("overview");
  const [bootIndex, setBootIndex] = useState(0);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Persistent case context — follow-ups refine the same case rather than reset.
  const caseContextRef = useRef<{
    medicines: Set<string>;
    conditions: Set<string>;
    allergies: Set<string>;
    age?: number;
    weight?: number;
  }>({
    medicines: new Set(),
    conditions: new Set(),
    allergies: new Set(),
  });

  /* ---------- Boot sequence ---------- */
  useEffect(() => {
    if (phase !== "boot") return;
    setBootIndex(0);
    let i = 0;
    const tick = () => {
      i += 1;
      setBootIndex(i);
      if (i >= BOOT_LINES.length) {
        // After last line, drop the initial intake card.
        setTimeout(() => {
          setMessages([
            {
              id: `intake-${Date.now()}`,
              role: "intake",
              acknowledgment: `I have analyzed ${PATIENT_OVERVIEW.patientName}'s intake form.`,
              symptoms: PATIENT_OVERVIEW.symptoms,
              confirmed: false,
            },
          ]);
          setPhase("active");
        }, 480);
        return;
      }
      setTimeout(tick, 520);
    };
    const t = setTimeout(tick, 600);
    return () => clearTimeout(t);
  }, [phase]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, bootIndex, phase]);

  function handleConfirmIntake(id: string) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id && m.role === "intake" ? { ...m, confirmed: true } : m)),
    );
    // Seed persistent context with the verified intake.
    PATIENT_OVERVIEW.symptoms.forEach((s) =>
      caseContextRef.current.conditions.add(s.toLowerCase()),
    );
    // Auto-prompt next step.
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: `sys-${Date.now()}`,
          role: "intake",
          acknowledgment:
            "Intake verified. Add a clinical note or proposed medication below to continue the workup.",
          symptoms: [],
          confirmed: true,
        },
      ]);
    }, 250);
  }

  async function handleSend(text?: string) {
    const note = (text ?? draft).trim();
    if (!note || busy) return;

    const userId = `u-${Date.now()}`;
    const aId = `a-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: note },
      { id: aId, role: "assistant", status: "thinking" },
    ]);
    setDraft("");
    setBusy(true);

    try {
      const parsed = await parseClinicalNote(note);

      // Merge parsed entities into persistent case context.
      parsed.medicines.forEach((m) => caseContextRef.current.medicines.add(m));
      parsed.current_medications.forEach((m) =>
        caseContextRef.current.medicines.add(m),
      );
      parsed.conditions.forEach((c) => caseContextRef.current.conditions.add(c));
      parsed.allergies.forEach((a) => caseContextRef.current.allergies.add(a));
      if (parsed.age != null) caseContextRef.current.age = parsed.age;
      if (parsed.weight != null) caseContextRef.current.weight = parsed.weight;

      // Build the request from the FULL accumulated case context.
      const ctx = caseContextRef.current;
      const mergedParsed: ParsedClinicalNote = {
        ...parsed,
        medicines: parsed.medicines.length ? parsed.medicines : Array.from(ctx.medicines),
        current_medications: Array.from(ctx.medicines).filter(
          (m) => !parsed.medicines.includes(m),
        ),
        conditions: Array.from(ctx.conditions),
        allergies: Array.from(ctx.allergies),
        age: ctx.age,
        weight: ctx.weight,
      };

      const req = parsedNoteToSafetyRequest(mergedParsed, defaults);

      if (req.medicines.length === 0) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aId
              ? {
                  ...(m as AssistantMsg),
                  status: "error",
                  parsed: mergedParsed,
                  errorText:
                    'No medication detected. Name the drug explicitly — e.g. "Considering furosemide 40mg PO."',
                }
              : m,
          ),
        );
        return;
      }

      const res = await runSafetyCheck(req);
      const reasoning = buildReasoning(mergedParsed, res);
      const recommendation = buildRecommendation(res);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === aId
            ? {
                ...(m as AssistantMsg),
                status: "ready",
                parsed: mergedParsed,
                request: req,
                response: res,
                reasoning,
                recommendation,
              }
            : m,
        ),
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aId
            ? {
                ...(m as AssistantMsg),
                status: "error",
                errorText:
                  "Engine unreachable. Doctor review required before any prescribing decision.",
              }
            : m,
        ),
      );
    } finally {
      setBusy(false);
      taRef.current?.focus();
    }
  }

  function handleKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    void handleSend();
  }

  /* ---------- Render ---------- */

  return (
    <div className="chat-noir overflow-hidden rounded-xl">
      <AnimatePresence mode="wait">
        {phase === "overview" && (
          <motion.div
            key="overview"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <PatientOverview onStart={() => setPhase("boot")} />
          </motion.div>
        )}

        {(phase === "boot" || phase === "active") && (
          <motion.div
            key="workspace"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="flex h-[720px] flex-col"
          >
            <StatusBar
              showInfo={showInfo}
              onToggleInfo={() => setShowInfo((v) => !v)}
            />

            <AnimatePresence>
              {showInfo && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="overflow-hidden border-b"
                  style={{ borderColor: "var(--noir-border-soft)" }}
                >
                  <InfoStrip />
                </motion.div>
              )}
            </AnimatePresence>

            <div
              ref={scrollRef}
              className="noir-scrollbar flex-1 overflow-y-auto px-4 py-6 sm:px-8"
            >
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
                {/* Boot lines — always visible at top of the thread */}
                <BootStream
                  lines={BOOT_LINES.slice(0, bootIndex)}
                  active={phase === "boot"}
                />

                {/* Conversation thread */}
                <AnimatePresence initial={false}>
                  {messages.map((m) => {
                    if (m.role === "user") return <UserBubble key={m.id} msg={m} />;
                    if (m.role === "intake")
                      return (
                        <IntakeBlock
                          key={m.id}
                          msg={m}
                          onConfirm={() => handleConfirmIntake(m.id)}
                        />
                      );
                    return (
                      <AssistantBubble
                        key={m.id}
                        msg={m}
                        onPromote={() => {
                          if (m.request && m.response)
                            onPromoteToCase(m.request, m.response);
                        }}
                      />
                    );
                  })}
                </AnimatePresence>
              </div>
            </div>

            {/* Composer */}
            <div
              className="border-t px-4 py-4 sm:px-8"
              style={{ borderColor: "var(--noir-border-soft)" }}
            >
              <form
                onSubmit={handleSubmit}
                className="noir-input mx-auto flex w-full max-w-3xl items-end gap-2 px-3 py-2"
              >
                <textarea
                  ref={taRef}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Add clinical notes..."
                  rows={1}
                  disabled={phase === "boot"}
                  className="noir-mono block max-h-32 min-h-[1.5rem] w-full resize-none bg-transparent px-1 py-1 text-[13px] leading-relaxed text-[var(--noir-text)] focus:outline-none disabled:opacity-50"
                />
                <button
                  type="submit"
                  aria-label="Send"
                  disabled={!draft.trim() || busy || phase === "boot"}
                  className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md transition-all hover:bg-[var(--noir-neon-soft)] disabled:opacity-30"
                >
                  {busy ? (
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      style={{ color: "var(--noir-neon)" }}
                    />
                  ) : (
                    <Send
                      className="h-4 w-4"
                      style={{ color: "var(--noir-neon)" }}
                      strokeWidth={2.25}
                    />
                  )}
                </button>
              </form>
              <p
                className="noir-mono mx-auto mt-2 max-w-3xl text-center text-[10px]"
                style={{ color: "var(--noir-text-faint)" }}
              >
                CONTEXT PERSISTED · DOCTOR REVIEW REQUIRED FOR ALL OUTPUTS
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ---------- Phase 1: Patient Overview ---------- */

function PatientOverview({ onStart }: { onStart: () => void }) {
  return (
    <div className="px-4 py-8 sm:px-10 sm:py-10">
      <div className="noir-card mx-auto w-full max-w-2xl p-6 sm:p-8">
        <div className="mb-1 flex items-center gap-2">
          <span
            className="noir-mono text-[10px] font-bold tracking-[0.18em]"
            style={{ color: "var(--noir-text-faint)" }}
          >
            RECORD {PATIENT_OVERVIEW.recordId}
          </span>
        </div>
        <h2
          className="text-2xl font-bold tracking-tight sm:text-3xl"
          style={{ color: "var(--noir-text)" }}
        >
          Patient Overview
        </h2>
        <p
          className="mt-3 text-sm leading-relaxed sm:text-[15px]"
          style={{ color: "var(--noir-text-dim)" }}
        >
          {PATIENT_OVERVIEW.summary}
        </p>

        <div className="noir-card-inset mt-6 p-5">
          <div className="mb-3 flex items-center gap-2">
            <Thermometer
              className="h-4 w-4"
              style={{ color: "var(--noir-neon)" }}
              strokeWidth={2.25}
            />
            <h3
              className="noir-mono text-xs font-bold tracking-[0.18em]"
              style={{ color: "var(--noir-neon)" }}
            >
              RECORDED SYMPTOMS
            </h3>
          </div>
          <ul className="space-y-2.5">
            {PATIENT_OVERVIEW.symptoms.map((s) => (
              <li
                key={s}
                className="flex items-center gap-3 text-sm"
                style={{ color: "var(--noir-text)" }}
              >
                <span
                  className="h-1.5 w-1.5 flex-shrink-0 rounded-full"
                  style={{
                    background: "var(--noir-neon)",
                    boxShadow: "0 0 8px var(--noir-neon)",
                  }}
                />
                {s}
              </li>
            ))}
          </ul>
        </div>

        <button
          type="button"
          onClick={onStart}
          className="noir-cta mt-6 flex w-full items-center justify-center gap-2 px-6 py-3.5 text-[13px]"
        >
          Start Diagnosis
          <ChevronRight className="h-4 w-4" strokeWidth={2.5} />
        </button>
      </div>
    </div>
  );
}

/* ---------- Status bar ---------- */

function StatusBar({
  showInfo,
  onToggleInfo,
}: {
  showInfo: boolean;
  onToggleInfo: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between border-b px-4 py-3 sm:px-6"
      style={{ borderColor: "var(--noir-border-soft)" }}
    >
      <div className="flex items-center gap-2.5">
        <span className="noir-pulse" aria-hidden />
        <h2
          className="text-sm font-bold tracking-tight"
          style={{ color: "var(--noir-text)" }}
        >
          Logic Engine Active
        </h2>
      </div>
      <button
        type="button"
        onClick={onToggleInfo}
        className="noir-mono flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-bold tracking-[0.18em] transition-colors"
        style={{
          borderColor: "var(--noir-border)",
          color: showInfo ? "var(--noir-neon)" : "var(--noir-text-dim)",
        }}
      >
        <UserRound className="h-3.5 w-3.5" strokeWidth={2.25} />
        VIEW <span style={{ color: "var(--noir-text)" }}>INFO</span>
      </button>
    </div>
  );
}

function InfoStrip() {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1.5 px-4 py-3 text-[11px] sm:px-6">
      {[
        ["Patient", PATIENT_OVERVIEW.patientName],
        ["Record", PATIENT_OVERVIEW.recordId],
        ["Status", "Fluid Overload Workup"],
        ["Engine", "Fail-safe v1"],
      ].map(([k, v]) => (
        <div key={k} className="flex items-center gap-1.5">
          <span
            className="noir-mono uppercase tracking-[0.14em]"
            style={{ color: "var(--noir-text-faint)" }}
          >
            {k}
          </span>
          <span style={{ color: "var(--noir-text)" }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- Boot stream ---------- */

function BootStream({ lines, active }: { lines: string[]; active: boolean }) {
  if (lines.length === 0) return null;
  return (
    <div className="space-y-1.5 text-center">
      {lines.map((l, i) => (
        <motion.p
          key={l + i}
          initial={{ opacity: 0 }}
          animate={{ opacity: i === lines.length - 1 && active ? 0.95 : 0.55 }}
          transition={{ duration: 0.25 }}
          className="noir-mono text-[11px] tracking-[0.16em]"
          style={{ color: "var(--noir-neon)" }}
        >
          {l}
          {i === lines.length - 1 && active && <span className="noir-caret" />}
        </motion.p>
      ))}
    </div>
  );
}

/* ---------- Bubbles ---------- */

function UserBubble({ msg }: { msg: UserMsg }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="flex justify-end"
    >
      <div
        className="max-w-[80%] rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed"
        style={{
          background: "var(--noir-surface-2)",
          color: "var(--noir-text)",
          border: "1px solid var(--noir-border-soft)",
        }}
      >
        {msg.content}
      </div>
    </motion.div>
  );
}

function IntakeBlock({
  msg,
  onConfirm,
}: {
  msg: IntakeMsg;
  onConfirm: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="space-y-3"
    >
      {/* Acknowledgment bubble */}
      <div className="flex max-w-[80%] items-start gap-3">
        <div className="noir-card-inset px-4 py-3">
          <div className="mb-1.5 flex items-center gap-2">
            <Brain
              className="h-3.5 w-3.5"
              style={{ color: "var(--noir-neon)" }}
              strokeWidth={2.25}
            />
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "var(--noir-text)" }}>
            {msg.acknowledgment}
          </p>
        </div>
      </div>

      {/* Verify intake card */}
      {msg.symptoms.length > 0 && (
        <div className="noir-card p-5">
          <div className="mb-3 flex items-center gap-2">
            <UserRound
              className="h-4 w-4"
              style={{ color: "var(--noir-neon)" }}
              strokeWidth={2.25}
            />
            <h3
              className="noir-mono text-xs font-bold tracking-[0.18em]"
              style={{ color: "var(--noir-neon)" }}
            >
              VERIFY INTAKE DATA:
            </h3>
          </div>
          <ul className="space-y-2">
            {msg.symptoms.map((s) => (
              <li
                key={s}
                className="noir-card-inset flex items-center gap-3 px-4 py-2.5 text-sm"
                style={{ color: "var(--noir-text)" }}
              >
                <CheckCircle2
                  className="h-4 w-4 flex-shrink-0"
                  style={{ color: "var(--noir-neon)" }}
                  strokeWidth={2.25}
                />
                {s}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={onConfirm}
            disabled={msg.confirmed}
            className="noir-cta mt-4 flex w-full items-center justify-center gap-2 px-4 py-3 text-[12px] disabled:opacity-50"
          >
            {msg.confirmed ? (
              <>
                <CheckCircle2 className="h-4 w-4" strokeWidth={2.5} />
                Intake Confirmed
              </>
            ) : (
              "Confirm & Start Analysis"
            )}
          </button>
        </div>
      )}
    </motion.div>
  );
}

function AssistantBubble({
  msg,
  onPromote,
}: {
  msg: AssistantMsg;
  onPromote: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="flex w-full"
    >
      <div className="w-full space-y-3">
        {msg.status === "thinking" && (
          <div className="noir-card-inset flex items-center gap-2.5 px-4 py-3">
            <Loader2
              className="h-3.5 w-3.5 animate-spin"
              style={{ color: "var(--noir-neon)" }}
            />
            <span
              className="noir-mono text-[11px] tracking-[0.14em]"
              style={{ color: "var(--noir-text-dim)" }}
            >
              ANALYZING · QUERYING SAFETY ENGINE...
            </span>
          </div>
        )}

        {msg.status === "error" && (
          <div
            className="noir-card-inset flex items-start gap-2.5 px-4 py-3"
            style={{ borderColor: "var(--noir-warning)" }}
          >
            <AlertTriangle
              className="mt-0.5 h-4 w-4 flex-shrink-0"
              style={{ color: "var(--noir-warning)" }}
              strokeWidth={2.25}
            />
            <p className="text-sm" style={{ color: "var(--noir-text)" }}>
              {msg.errorText}
            </p>
          </div>
        )}

        {msg.status === "ready" && msg.parsed && msg.response && (
          <StructuredAnswer
            parsed={msg.parsed}
            response={msg.response}
            reasoning={msg.reasoning ?? ""}
            recommendation={msg.recommendation ?? ""}
            onPromote={onPromote}
          />
        )}
      </div>
    </motion.div>
  );
}

/* ---------- Structured answer ---------- */

function StructuredAnswer({
  parsed,
  response,
  reasoning,
  recommendation,
  onPromote,
}: {
  parsed: ParsedClinicalNote;
  response: SafetyCheckResponse;
  reasoning: string;
  recommendation: string;
  onPromote: () => void;
}) {
  const tone =
    response.overall_risk === "HIGH"
      ? "danger"
      : response.overall_risk === "MEDIUM"
        ? "warning"
        : "success";

  const issues = [
    ...response.interactions.map((i) => ({
      label: `${i.drug_a} × ${i.drug_b}`,
      severity: i.severity,
      detail: i.mechanism,
    })),
    ...response.allergies.map((a) => ({
      label: `${a.drug} allergy (${a.allergen})`,
      severity: a.severity,
      detail: a.reason,
    })),
    ...response.contraindications.map((c) => ({
      label: `${c.drug} vs ${c.condition}`,
      severity: c.severity ?? "MEDIUM",
      detail: c.reasoning,
    })),
  ];

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{
        hidden: { opacity: 0 },
        show: { opacity: 1, transition: { staggerChildren: 0.07 } },
      }}
      className="space-y-3"
    >
      <NoirSection
        icon={<ScanSearch className="h-3.5 w-3.5" strokeWidth={2.25} />}
        title="EXTRACTED ENTITIES"
      >
        <div className="flex flex-wrap gap-1.5">
          <NoirChipGroup
            label="MEDS"
            items={parsed.medicines}
            icon={<Pill className="h-3 w-3" />}
          />
          <NoirChipGroup
            label="ON"
            items={parsed.current_medications}
            icon={<HeartPulse className="h-3 w-3" />}
          />
          <NoirChipGroup
            label="DX"
            items={parsed.conditions}
            icon={<Stethoscope className="h-3 w-3" />}
          />
          <NoirChipGroup label="ALLERGY" items={parsed.allergies} tone="danger" />
          {parsed.age != null && <NoirChip>{parsed.age} y/o</NoirChip>}
          {parsed.weight != null && <NoirChip>{parsed.weight} kg</NoirChip>}
        </div>
      </NoirSection>

      <NoirSection
        icon={<AlertTriangle className="h-3.5 w-3.5" strokeWidth={2.25} />}
        title="RISK ANALYSIS"
        toneAccent={tone}
      >
        <div className="flex items-center gap-3">
          <span
            className="noir-mono rounded px-2 py-0.5 text-[10px] font-bold tracking-[0.16em]"
            style={{
              background:
                tone === "danger"
                  ? "var(--noir-danger)"
                  : tone === "warning"
                    ? "var(--noir-warning)"
                    : "var(--noir-neon)",
              color: "oklch(0.16 0.04 150)",
            }}
          >
            {response.overall_risk} RISK
          </span>
          <div className="flex-1">
            <RiskMeter value={response.patient_risk_score} size="sm" showValue={false} />
          </div>
          <span
            className="noir-mono text-sm font-bold tabular-nums"
            style={{ color: "var(--noir-text)" }}
          >
            {Math.round(response.patient_risk_score)}
            <span
              className="text-[10px] font-semibold"
              style={{ color: "var(--noir-text-faint)" }}
            >
              /100
            </span>
          </span>
        </div>
        {issues.length > 0 ? (
          <ul className="mt-3 space-y-1.5">
            {issues.slice(0, 4).map((it, idx) => (
              <li key={idx} className="noir-card-inset flex items-start gap-2.5 p-2.5">
                <SeverityBadge severity={it.severity} />
                <div className="min-w-0 flex-1">
                  <p
                    className="text-xs font-bold"
                    style={{ color: "var(--noir-text)" }}
                  >
                    {it.label}
                  </p>
                  <p
                    className="text-[11px] leading-relaxed"
                    style={{ color: "var(--noir-text-dim)" }}
                  >
                    {it.detail}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p
            className="noir-mono mt-2 text-[11px] tracking-[0.12em]"
            style={{ color: "var(--noir-neon)" }}
          >
            ✓ NO INTERACTIONS, ALLERGIES, OR CONTRAINDICATIONS FLAGGED.
          </p>
        )}
      </NoirSection>

      <NoirSection
        icon={<FlaskConical className="h-3.5 w-3.5" strokeWidth={2.25} />}
        title="CLINICAL REASONING"
      >
        <p
          className="text-[12.5px] leading-relaxed"
          style={{ color: "var(--noir-text-dim)" }}
        >
          {reasoning}
        </p>
      </NoirSection>

      <NoirSection
        icon={<ShieldCheck className="h-3.5 w-3.5" strokeWidth={2.25} />}
        title="RECOMMENDATION"
        toneAccent={response.safe_to_prescribe ? "success" : "danger"}
      >
        <p
          className="text-[12.5px] font-medium leading-relaxed"
          style={{ color: "var(--noir-text)" }}
        >
          {recommendation}
        </p>
      </NoirSection>

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          onClick={onPromote}
          className="noir-cta inline-flex items-center gap-1.5 px-3 py-2 text-[10px]"
        >
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.5} />
          View Detailed Analysis
        </button>
        <button
          type="button"
          onClick={onPromote}
          className="noir-mono inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em] transition-colors"
          style={{
            borderColor: "var(--noir-border)",
            color: "var(--noir-text)",
          }}
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
          Add to Case
        </button>
        <button
          type="button"
          className="noir-mono inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.14em]"
          style={{
            borderColor: "var(--noir-border)",
            color: "var(--noir-text-dim)",
          }}
        >
          <Activity className="h-3.5 w-3.5" strokeWidth={2.5} />
          Run Full Safety Check
        </button>
      </div>
    </motion.div>
  );
}

/* ---------- Reasoning + recommendation ---------- */

function buildReasoning(parsed: ParsedClinicalNote, res: SafetyCheckResponse): string {
  const bits: string[] = [];
  if (res.interactions.length > 0) {
    const h = res.interactions.find((i) => i.severity === "HIGH") ?? res.interactions[0];
    bits.push(
      `${h.drug_a} and ${h.drug_b} share an overlapping pharmacologic pathway (${h.mechanism.toLowerCase()}), driving the elevated score.`,
    );
  }
  if (res.allergies.length > 0) {
    const a = res.allergies[0];
    bits.push(
      `Documented ${a.allergen} allergy cross-reacts with ${a.drug}; non-negotiable per safety policy.`,
    );
  }
  if (res.contraindications.length > 0) {
    const c = res.contraindications[0];
    bits.push(
      `${c.drug} is contraindicated against the patient's ${c.condition}: ${c.reasoning.toLowerCase()}`,
    );
  }
  if (bits.length === 0) {
    bits.push(
      `No conflicting pharmacology detected for ${parsed.medicines.join(", ") || "the proposed regimen"} given the patient's profile.`,
    );
  }
  if (parsed.age != null && parsed.age >= 65) {
    bits.push(
      `Patient is geriatric (${parsed.age} y/o) — Beers Criteria apply; review dosing.`,
    );
  }
  return bits.join(" ");
}

function buildRecommendation(res: SafetyCheckResponse): string {
  if (!res.safe_to_prescribe) {
    const altBit =
      res.interactions[0]?.recommendation ??
      res.allergies[0]?.reason ??
      "Use a non-conflicting alternative agent.";
    return `Do not prescribe as-is. ${altBit} Document the decision and require a second-clinician sign-off.`;
  }
  if (res.requires_doctor_review) {
    return "Prescribing is permissible, but doctor review is required before dispensing. Verify dose, route, and renal/hepatic adjustments.";
  }
  return "Safe to prescribe with standard monitoring. Counsel patient on common side effects and follow-up timing.";
}

/* ---------- Atoms ---------- */

function NoirSection({
  icon,
  title,
  children,
  toneAccent,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
  toneAccent?: "danger" | "warning" | "success";
}) {
  const accent =
    toneAccent === "danger"
      ? "var(--noir-danger)"
      : toneAccent === "warning"
        ? "var(--noir-warning)"
        : toneAccent === "success"
          ? "var(--noir-neon)"
          : "var(--noir-border-soft)";
  return (
    <motion.section
      variants={{
        hidden: { opacity: 0, y: 6 },
        show: { opacity: 1, y: 0, transition: { duration: 0.22 } },
      }}
      className={cn("noir-card p-3.5")}
      style={{ borderColor: accent }}
    >
      <p
        className="noir-mono mb-2 flex items-center gap-1.5 text-[10px] font-bold tracking-[0.18em]"
        style={{ color: "var(--noir-neon)" }}
      >
        <span>{icon}</span>
        {title}
      </p>
      {children}
    </motion.section>
  );
}

function NoirChipGroup({
  label,
  items,
  icon,
  tone,
}: {
  label: string;
  items: string[];
  icon?: React.ReactNode;
  tone?: "danger";
}) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span
        className="noir-mono text-[9px] font-bold tracking-[0.18em]"
        style={{ color: "var(--noir-text-faint)" }}
      >
        {label}:
      </span>
      {items.map((t) => (
        <NoirChip key={t} tone={tone} icon={icon}>
          {t}
        </NoirChip>
      ))}
    </div>
  );
}

function NoirChip({
  children,
  tone,
  icon,
}: {
  children: React.ReactNode;
  tone?: "danger";
  icon?: React.ReactNode;
}) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-semibold"
      style={{
        borderColor:
          tone === "danger" ? "var(--noir-danger)" : "var(--noir-border)",
        color: tone === "danger" ? "var(--noir-danger)" : "var(--noir-text)",
        background: tone === "danger" ? "transparent" : "var(--noir-bg)",
      }}
    >
      {icon}
      {children}
    </span>
  );
}

// Keep imports referenced even when unused branches compile out.
void Terminal;
void Info;
