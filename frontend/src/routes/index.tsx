import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { ShieldCheck, History, Hospital, Activity } from "lucide-react";
import { WorkspacePanel } from "@/components/safety/WorkspacePanel";
import { ResultsPanel } from "@/components/safety/ResultsPanel";
import { HistoryDrawer } from "@/components/safety/HistoryDrawer";
import { runSafetyCheck } from "@/lib/safety-api";
import { saveHistoryEntry } from "@/lib/history-store";
import type {
  HistoryEntry,
  SafetyCheckRequest,
  SafetyCheckResponse,
} from "@/lib/safety-types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Clinical Drug Safety Engine — CDSS Dashboard" },
      {
        name: "description",
        content:
          "Hospital-grade clinical decision support for drug-drug interactions, allergies, contraindications, and patient risk scoring.",
      },
      {
        property: "og:title",
        content: "Clinical Drug Safety Engine",
      },
      {
        property: "og:description",
        content:
          "Real-time safety checks for prescribers — interactions, allergies, contraindications, risk scoring.",
      },
    ],
  }),
  component: SafetyDashboardPage,
});

function SafetyDashboardPage() {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<SafetyCheckResponse | null>(null);
  const [request, setRequest] = useState<SafetyCheckRequest | null>(null);
  const [entry, setEntry] = useState<HistoryEntry | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyVersion, setHistoryVersion] = useState(0);

  async function handleSubmit(req: SafetyCheckRequest) {
    setLoading(true);
    setRequest(req);
    setResponse(null);
    setEntry(null);
    try {
      const res = await runSafetyCheck(req);
      const saved = saveHistoryEntry(req, res);
      setResponse(res);
      setEntry(saved);
      setHistoryVersion((v) => v + 1);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setResponse(null);
    setRequest(null);
    setEntry(null);
  }

  function handleSelectHistory(h: HistoryEntry) {
    setRequest(h.request);
    setResponse(h.response);
    setEntry(h);
  }

  return (
    <div className="relative min-h-screen bg-background">
      <Header
        onOpenHistory={() => setHistoryOpen(true)}
        sourceLabel={response?.system_info.source}
      />

      <main className="mx-auto max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <aside className="lg:col-span-4 xl:col-span-4">
            <div className="lg:sticky lg:top-[88px]">
              <WorkspacePanel
                loading={loading}
                onSubmit={handleSubmit}
                onReset={handleReset}
                onChatResult={(req, res) => {
                  const saved = saveHistoryEntry(req, res);
                  setRequest(req);
                  setResponse(res);
                  setEntry(saved);
                  setHistoryVersion((v) => v + 1);
                }}
              />
            </div>
          </aside>
          <section className="lg:col-span-8 xl:col-span-8">
            <ResultsPanel
              loading={loading}
              data={response}
              request={request}
              entry={entry}
            />
          </section>
        </div>

        <Footer />
      </main>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        refreshKey={historyVersion}
        onSelect={handleSelectHistory}
      />
    </div>
  );
}

function Header({
  onOpenHistory,
  sourceLabel,
}: {
  onOpenHistory: () => void;
  sourceLabel?: string;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/60">
      <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-primary text-primary-foreground shadow-clinical">
            <Hospital className="h-5 w-5" strokeWidth={2.5} />
          </span>
          <div className="leading-tight">
            <h1 className="flex items-center gap-2 text-[15px] font-bold tracking-tight text-foreground">
              Clinical Drug Safety Engine
              <span className="hidden rounded bg-accent px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-primary sm:inline">
                CDSS · v1
              </span>
            </h1>
            <p className="text-[11px] text-muted-foreground">
              Real-time prescribing decision support
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 sm:flex">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
            </span>
            <span className="text-[11px] font-semibold text-muted-foreground">
              Engine{" "}
              <strong className="text-foreground">
                {sourceLabel ?? "online"}
              </strong>
            </span>
          </div>

          <button
            type="button"
            onClick={onOpenHistory}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-2 text-xs font-semibold text-foreground transition-colors hover:border-primary hover:text-primary"
          >
            <History className="h-4 w-4" />
            History
          </button>

          <span className="hidden items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-bold uppercase tracking-wider text-primary-foreground md:inline-flex">
            <ShieldCheck className="h-4 w-4" strokeWidth={2.5} />
            Fail-safe mode
          </span>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="mt-10 border-t border-border pt-6 pb-2">
      <div className="flex flex-col gap-2 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-center gap-1.5">
          <Activity className="h-3 w-3" />
          For clinical decision support only. Always verify with current
          prescribing information.
        </p>
        <p className="tabular-nums">
          Clinical Drug Safety Engine · Built for hospital-grade workflows
        </p>
      </div>
    </footer>
  );
}
