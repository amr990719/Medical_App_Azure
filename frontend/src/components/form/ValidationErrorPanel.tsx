import { useEffect, useRef } from "react";
import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

export interface PanelError {
  message: string;
  field?: string;
}

export interface ValidationErrorPanelProps {
  errors: readonly PanelError[];
  className?: string;
}

/**
 * Every server validation error at once (PROMPT.md §9.1, §22), above the form card.
 * Scrolls itself into view whenever a new set of errors arrives.
 */
export function ValidationErrorPanel({ errors, className }: ValidationErrorPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const hasErrors = errors.length > 0;

  useEffect(() => {
    if (hasErrors) ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [errors, hasErrors]);

  if (!hasErrors) return null;

  return (
    <div
      ref={ref}
      role="alert"
      className={cx(
        "scroll-mt-28 rounded-lg border border-s-4 border-danger/30 border-s-danger bg-danger-light p-4 text-charcoal",
        className,
      )}
    >
      <p className="flex items-center gap-2 font-bold text-danger">
        <Icon name="alert" />
        {ar.errors.panelTitle}
      </p>
      <ul className="mt-2 list-disc space-y-1 ps-9 marker:text-danger">
        {errors.map((error, index) => (
          <li key={`${error.field ?? "general"}-${index}`}>{error.message}</li>
        ))}
      </ul>
    </div>
  );
}
