import { useId, useState, type KeyboardEvent } from "react";
import { X, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

interface TagInputProps {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  helperText?: string;
  suggestions?: string[];
  className?: string;
}

export function TagInput({
  label,
  value,
  onChange,
  placeholder,
  helperText,
  suggestions,
  className,
}: TagInputProps) {
  const id = useId();
  const [draft, setDraft] = useState("");

  function addTag(raw: string) {
    const items = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (items.length === 0) return;
    const set = new Set(value.map((v) => v.toLowerCase()));
    const next = [...value];
    for (const it of items) {
      if (!set.has(it.toLowerCase())) {
        next.push(it);
        set.add(it.toLowerCase());
      }
    }
    onChange(next);
    setDraft("");
  }

  function removeTag(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (draft.trim()) addTag(draft);
    } else if (e.key === "Backspace" && !draft && value.length > 0) {
      removeTag(value.length - 1);
    }
  }

  return (
    <div className={cn("space-y-1.5", className)}>
      <label
        htmlFor={id}
        className="block text-xs font-semibold uppercase tracking-wide text-foreground"
      >
        {label}
      </label>
      <div
        className={cn(
          "flex min-h-[44px] flex-wrap items-center gap-1.5 rounded-md border border-input bg-surface px-2 py-1.5",
          "focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20",
        )}
      >
        {value.map((tag, i) => (
          <span
            key={`${tag}-${i}`}
            className="inline-flex items-center gap-1 rounded-md bg-accent px-2 py-0.5 text-sm font-medium text-accent-foreground"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(i)}
              aria-label={`Remove ${tag}`}
              className="rounded-sm text-accent-foreground/70 hover:text-danger"
            >
              <X className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => draft.trim() && addTag(draft)}
          placeholder={value.length === 0 ? placeholder : ""}
          className="flex-1 min-w-[120px] bg-transparent px-1 py-1 text-sm outline-none placeholder:text-muted-foreground"
        />
        {draft.trim() && (
          <button
            type="button"
            onClick={() => addTag(draft)}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-xs font-semibold text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-3 w-3" /> Add
          </button>
        )}
      </div>
      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {suggestions
            .filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase()))
            .slice(0, 6)
            .map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => addTag(s)}
                className="rounded-md border border-dashed border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
              >
                + {s}
              </button>
            ))}
        </div>
      )}
      {helperText && (
        <p className="text-[11px] text-muted-foreground">{helperText}</p>
      )}
    </div>
  );
}
