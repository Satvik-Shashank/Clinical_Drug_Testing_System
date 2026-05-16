import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface ClinicalCardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  count?: number;
  countTone?: "danger" | "warning" | "success" | "info" | "muted";
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  tone?: "default" | "danger" | "warning" | "success";
}

const TONE_BORDER: Record<NonNullable<ClinicalCardProps["tone"]>, string> = {
  default: "border-border",
  danger: "border-danger/40",
  warning: "border-warning/50",
  success: "border-success/40",
};

const COUNT_TONE: Record<NonNullable<ClinicalCardProps["countTone"]>, string> = {
  danger: "bg-danger text-danger-foreground",
  warning: "bg-warning text-warning-foreground",
  success: "bg-success text-success-foreground",
  info: "bg-info text-info-foreground",
  muted: "bg-muted text-muted-foreground",
};

export function ClinicalCard({
  title,
  subtitle,
  icon,
  count,
  countTone = "muted",
  actions,
  children,
  className,
  bodyClassName,
  tone = "default",
}: ClinicalCardProps) {
  return (
    <section
      className={cn(
        "rounded-lg border bg-card shadow-clinical",
        TONE_BORDER[tone],
        className,
      )}
    >
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon ? (
              <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-accent text-primary">
                {icon}
              </span>
            ) : null}
            <div className="min-w-0">
              {title ? (
                <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-foreground">
                  <span className="truncate">{title}</span>
                  {typeof count === "number" && (
                    <span
                      className={cn(
                        "inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[11px] font-bold tabular-nums",
                        COUNT_TONE[countTone],
                      )}
                    >
                      {count}
                    </span>
                  )}
                </h3>
              ) : null}
              {subtitle ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
              ) : null}
            </div>
          </div>
          {actions ? (
            <div className="flex flex-shrink-0 items-center gap-2">{actions}</div>
          ) : null}
        </header>
      )}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}
