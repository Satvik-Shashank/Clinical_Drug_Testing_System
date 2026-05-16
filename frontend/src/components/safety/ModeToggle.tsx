import { ClipboardList, MessageSquareText } from "lucide-react";
import { cn } from "@/lib/utils";

export type InputMode = "form" | "chat";

interface Props {
  mode: InputMode;
  onChange: (m: InputMode) => void;
}

export function ModeToggle({ mode, onChange }: Props) {
  return (
    <div
      role="tablist"
      aria-label="Input mode"
      className="inline-flex w-full items-center gap-1 rounded-md border border-border bg-muted/40 p-1"
    >
      <Tab
        active={mode === "form"}
        onClick={() => onChange("form")}
        icon={<ClipboardList className="h-3.5 w-3.5" strokeWidth={2.5} />}
        label="Form"
        hint="Structured input"
      />
      <Tab
        active={mode === "chat"}
        onClick={() => onChange("chat")}
        icon={<MessageSquareText className="h-3.5 w-3.5" strokeWidth={2.5} />}
        label="Clinical Notes"
        hint="Natural language"
      />
    </div>
  );
}

function Tab({
  active,
  onClick,
  icon,
  label,
  hint,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "group flex flex-1 items-center justify-center gap-1.5 rounded-[5px] px-3 py-2 text-xs font-bold uppercase tracking-wide transition-all",
        active
          ? "bg-card text-primary shadow-clinical"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      <span className={cn(active ? "text-primary" : "text-muted-foreground")}>
        {icon}
      </span>
      <span className="flex flex-col items-start leading-tight sm:flex-row sm:items-center sm:gap-1.5">
        {label}
        <span
          className={cn(
            "text-[9px] font-medium normal-case tracking-normal",
            active ? "text-muted-foreground" : "text-muted-foreground/70",
          )}
        >
          {hint}
        </span>
      </span>
    </button>
  );
}
