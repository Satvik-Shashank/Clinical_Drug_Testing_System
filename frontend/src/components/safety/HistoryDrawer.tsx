import { useEffect, useState } from "react";
import { History, X, Trash2, FileDown } from "lucide-react";
import type { HistoryEntry } from "@/lib/safety-types";
import { clearHistory, loadHistory } from "@/lib/history-store";
import { exportSafetyReportPdf } from "@/lib/pdf-export";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  refreshKey: number;
  onSelect: (entry: HistoryEntry) => void;
}

const RISK_COLOR = {
  HIGH: "bg-danger text-danger-foreground",
  MEDIUM: "bg-warning text-warning-foreground",
  LOW: "bg-success text-success-foreground",
} as const;

export function HistoryDrawer({ open, onClose, refreshKey, onSelect }: Props) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (open) setEntries(loadHistory());
  }, [open, refreshKey]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close history"
        onClick={onClose}
        className="flex-1 bg-foreground/30 backdrop-blur-sm"
      />
      {/* Drawer */}
      <aside className="flex h-full w-full max-w-md flex-col border-l border-border bg-surface shadow-clinical-lg">
        <header className="flex items-center justify-between border-b border-border px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-primary">
              <History className="h-4 w-4" strokeWidth={2.5} />
            </span>
            <div>
              <h2 className="text-sm font-bold uppercase tracking-wide text-foreground">
                Check History
              </h2>
              <p className="text-[11px] text-muted-foreground">
                Last {entries.length} of 25 checks (local device)
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => {
                clearHistory();
                setEntries([]);
              }}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-muted-foreground hover:bg-muted hover:text-danger"
              disabled={entries.length === 0}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-3">
          {entries.length === 0 ? (
            <p className="px-2 py-10 text-center text-sm text-muted-foreground">
              No previous checks yet.
            </p>
          ) : (
            <ul className="space-y-2">
              {entries.map((e) => (
                <li
                  key={e.id}
                  className="rounded-md border border-border bg-card p-3 transition-shadow hover:shadow-clinical"
                >
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(e);
                      onClose();
                    }}
                    className="block w-full text-left"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={cn(
                          "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
                          RISK_COLOR[e.response.overall_risk] ?? RISK_COLOR.MEDIUM,
                        )}
                      >
                        {e.response.overall_risk}
                      </span>
                      <span className="text-[11px] tabular-nums text-muted-foreground">
                        {new Date(e.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-semibold text-foreground line-clamp-1">
                      {e.request.medicines.join(", ") || "—"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      Age {e.request.patient_history.age} ·{" "}
                      {e.request.patient_history.weight} kg · Score{" "}
                      <strong className="text-foreground tabular-nums">
                        {Math.round(e.response.patient_risk_score)}
                      </strong>
                      /100
                    </p>
                  </button>
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      onClick={() => exportSafetyReportPdf(e)}
                      className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-semibold text-muted-foreground hover:border-primary hover:text-primary"
                    >
                      <FileDown className="h-3 w-3" />
                      PDF
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
