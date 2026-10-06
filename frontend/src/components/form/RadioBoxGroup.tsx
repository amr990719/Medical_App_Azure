import { useId } from "react";
import { cx } from "@/utils/cx";

export interface RadioBoxOption<T extends string> {
  value: T;
  label: string;
}

export interface RadioBoxGroupProps<T extends string> {
  label: string;
  name: string;
  options: readonly RadioBoxOption<T>[];
  value: T | "";
  onChange: (value: T) => void;
  disabled?: boolean;
  error?: string;
  className?: string;
}

/**
 * The paper form's tick boxes (`بشري / صيدلي / أسنان / بيطري`) as a real radio group:
 * native radios give keyboard arrows and screen-reader semantics; the visible box is the label.
 */
export function RadioBoxGroup<T extends string>({
  label,
  name,
  options,
  value,
  onChange,
  disabled = false,
  error,
  className,
}: RadioBoxGroupProps<T>) {
  const labelId = useId();
  const errorId = useId();

  return (
    <div className={cx("flex min-w-0 flex-col gap-1 md:flex-row md:items-center md:gap-2", className)}>
      <span id={labelId} className="shrink-0 font-bold text-charcoal">
        {label}
      </span>
      <div className="min-w-0">
        <div
          role="radiogroup"
          aria-labelledby={labelId}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          className="flex flex-wrap gap-1.5"
        >
          {options.map((option) => {
            const checked = option.value === value;
            return (
              <label
                key={option.value}
                className={cx(
                  "relative inline-flex min-h-9 select-none items-center border-[1.5px] px-3 font-bold print:min-h-7 print:px-2",
                  "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-teal-deep",
                  error ? "border-danger" : "border-paper-line",
                  checked
                    ? "bg-[#e2e4e8] text-ink shadow-[inset_0_2px_5px_rgb(0_0_0/0.28)]"
                    : "bg-paper text-charcoal hover:bg-smoke",
                  disabled ? "cursor-default opacity-80" : "cursor-pointer",
                )}
              >
                <input
                  type="radio"
                  className="sr-only"
                  name={name}
                  value={option.value}
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onChange(option.value)}
                />
                {option.label}
              </label>
            );
          })}
        </div>
        {error ? (
          <p id={errorId} className="mt-1 text-sm font-semibold text-danger">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
