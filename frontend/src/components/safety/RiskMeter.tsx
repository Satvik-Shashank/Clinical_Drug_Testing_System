import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface RiskMeterProps {
  value: number; // 0-100
  label?: string;
  size?: "sm" | "md" | "lg";
  showValue?: boolean;
  className?: string;
}

function bandFor(value: number) {
  if (value >= 67) return { fill: "bg-danger", text: "text-danger" };
  if (value >= 34) return { fill: "bg-warning", text: "text-warning" };
  return { fill: "bg-success", text: "text-success" };
}

export function RiskMeter({
  value,
  label,
  size = "md",
  showValue = true,
  className,
}: RiskMeterProps) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const band = bandFor(v);
  const h = size === "sm" ? "h-1.5" : size === "lg" ? "h-3" : "h-2";

  return (
    <div className={cn("w-full", className)}>
      {(label || showValue) && (
        <div className="mb-1.5 flex items-baseline justify-between gap-2">
          {label ? (
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {label}
            </span>
          ) : (
            <span />
          )}
          {showValue ? (
            <span className={cn("text-sm font-bold tabular-nums", band.text)}>
              {v}
              <span className="ml-0.5 text-[10px] font-semibold text-muted-foreground">
                /100
              </span>
            </span>
          ) : null}
        </div>
      )}
      <div
        className={cn("w-full overflow-hidden rounded-full bg-muted", h)}
        role="progressbar"
        aria-valuenow={v}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <motion.div
          key={v}
          className={cn("h-full", band.fill)}
          initial={{ width: 0 }}
          animate={{ width: `${v}%` }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
      </div>
    </div>
  );
}
