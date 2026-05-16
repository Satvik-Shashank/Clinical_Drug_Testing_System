import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/safety-types";
import { AlertTriangle, AlertOctagon, Info } from "lucide-react";

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
  withIcon?: boolean;
}

const STYLES: Record<
  Severity,
  { wrap: string; label: string; Icon: typeof AlertTriangle }
> = {
  HIGH: {
    wrap: "bg-danger text-danger-foreground border-danger",
    label: "HIGH",
    Icon: AlertOctagon,
  },
  MEDIUM: {
    wrap: "bg-warning text-warning-foreground border-warning",
    label: "MEDIUM",
    Icon: AlertTriangle,
  },
  LOW: {
    wrap: "bg-success text-success-foreground border-success",
    label: "LOW",
    Icon: Info,
  },
};

export function SeverityBadge({
  severity,
  className,
  withIcon = true,
}: SeverityBadgeProps) {
  const s = STYLES[severity] ?? STYLES.LOW;
  const Icon = s.Icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider",
        s.wrap,
        className,
      )}
    >
      {withIcon ? <Icon className="h-3 w-3" strokeWidth={2.5} /> : null}
      {s.label}
    </span>
  );
}
