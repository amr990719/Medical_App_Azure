import { useId, type InputHTMLAttributes } from "react";
import { digitsOnly } from "@/utils/digits";
import { cx } from "@/utils/cx";

export interface DashedFieldProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "size"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Digits only (Arabic digits normalized), LTR, numeric keyboard: years, phone, card numbers. */
  numeric?: boolean;
  error?: string;
}

/**
 * Paper-form field: bold label on the start side and a dashed underline "written in ink".
 * Below 768px the label sits above the input (PROMPT.md §9.4).
 */
export function DashedField({
  label,
  value,
  onChange,
  numeric = false,
  error,
  maxLength,
  dir,
  inputMode,
  className,
  id,
  ...rest
}: DashedFieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const errorId = `${inputId}-error`;

  return (
    <div className={cx("flex min-w-0 flex-col gap-1 md:flex-row md:items-end md:gap-2", className)}>
      <label htmlFor={inputId} className="shrink-0 font-bold text-charcoal">
        {label}
      </label>
      <div className="min-w-0 flex-1">
        <input
          id={inputId}
          value={value}
          maxLength={maxLength}
          dir={numeric ? "ltr" : dir}
          inputMode={numeric ? "numeric" : inputMode}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => {
            const raw = event.target.value;
            const next = numeric ? digitsOnly(raw) : raw;
            onChange(maxLength ? next.slice(0, maxLength) : next);
          }}
          className={cx(
            "w-full min-w-0 border-0 border-b-[1.5px] border-dashed bg-transparent px-1 py-0.5",
            "font-semibold text-ink outline-none placeholder:text-muted/70",
            "focus:border-solid focus:border-ink focus:bg-banana-light/60",
            numeric && "text-start tabular-nums",
            error ? "border-danger" : "border-paper-line",
            rest.readOnly && "cursor-default",
          )}
          {...rest}
        />
        {error ? (
          <p id={errorId} className="mt-1 text-sm font-semibold text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
