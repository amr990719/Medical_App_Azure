import { useId, type SelectHTMLAttributes } from "react";
import { cx } from "@/utils/cx";

export interface DashedSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange"> {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly { value: string; label: string }[];
  placeholder: string;
  error?: string;
}

/** DashedField's select twin (governorate): bold label, dashed underline, ink-blue value. */
export function DashedSelect({
  label,
  value,
  onChange,
  options,
  placeholder,
  error,
  className,
  ...rest
}: DashedSelectProps) {
  const id = useId();
  const errorId = `${id}-error`;
  return (
    <div className={cx("flex min-w-0 flex-col gap-1 md:flex-row md:items-end md:gap-2", className)}>
      <label htmlFor={id} className="shrink-0 font-bold text-charcoal">
        {label}
      </label>
      <div className="min-w-0 flex-1">
        <select
          id={id}
          value={value}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(event.target.value)}
          className={cx(
            "w-full min-w-0 cursor-pointer border-0 border-b-[1.5px] border-dashed bg-transparent px-1 py-0.5",
            "font-semibold text-ink outline-none focus:border-solid focus:border-ink focus:bg-banana-light/60",
            "disabled:cursor-default disabled:opacity-100 print:appearance-none",
            error ? "border-danger" : "border-paper-line",
            value === "" && "text-muted",
          )}
          {...rest}
        >
          <option value="">{placeholder}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value} className="text-charcoal">
              {option.label}
            </option>
          ))}
        </select>
        {error ? (
          <p id={errorId} className="mt-1 text-sm font-semibold text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
