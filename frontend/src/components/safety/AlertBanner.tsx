import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { AlertOctagon, AlertTriangle, CheckCircle2, Info } from "lucide-react";

type Tone = "danger" | "warning" | "success" | "info";

interface AlertBannerProps {
  tone: Tone;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

const TONES: Record<
  Tone,
  { wrap: string; iconWrap: string; Icon: typeof Info }
> = {
  danger: {
    wrap: "bg-danger-soft border-danger/40 text-foreground",
    iconWrap: "bg-danger text-danger-foreground",
    Icon: AlertOctagon,
  },
  warning: {
    wrap: "bg-warning-soft border-warning/50 text-foreground",
    iconWrap: "bg-warning text-warning-foreground",
    Icon: AlertTriangle,
  },
  success: {
    wrap: "bg-success-soft border-success/40 text-foreground",
    iconWrap: "bg-success text-success-foreground",
    Icon: CheckCircle2,
  },
  info: {
    wrap: "bg-info-soft border-info/40 text-foreground",
    iconWrap: "bg-info text-info-foreground",
    Icon: Info,
  },
};

export function AlertBanner({
  tone,
  title,
  description,
  actions,
  className,
}: AlertBannerProps) {
  const t = TONES[tone];
  const Icon = t.Icon;
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-lg border p-4 shadow-clinical",
        t.wrap,
        className,
      )}
    >
      <span
        className={cn(
          "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md",
          t.iconWrap,
        )}
      >
        <Icon className="h-4 w-4" strokeWidth={2.5} />
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-bold leading-tight text-foreground">{title}</p>
        {description ? (
          <p className="mt-1 text-sm leading-relaxed text-foreground/80">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex-shrink-0">{actions}</div> : null}
    </div>
  );
}
