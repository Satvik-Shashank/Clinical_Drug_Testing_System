import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface ExplainProps {
  title?: string;
  children: ReactNode;
  className?: string;
}

export function ExplainSection({
  title = "Explain this risk",
  children,
  className,
}: ExplainProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn("mt-2", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
        aria-expanded={open}
      >
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform",
            open && "rotate-180",
          )}
        />
        {title}
      </button>
      {open ? (
        <div className="mt-2 rounded-md border border-border bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
          {children}
        </div>
      ) : null}
    </div>
  );
}
