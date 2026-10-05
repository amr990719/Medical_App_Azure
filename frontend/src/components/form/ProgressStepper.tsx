import { Fragment } from "react";
import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

export type WizardStep = 1 | 2 | 3 | 4 | 5;
type StepState = "complete" | "current" | "upcoming";

export interface ProgressStepperProps {
  current: WizardStep;
  /** Steps the server validation reports complete (`steps_complete`). */
  completed: ReadonlySet<number>;
  className?: string;
}

/**
 * Five-step wizard progress (PROMPT.md §9.1): teal check when complete, pulsing banana circle
 * for the current step, grey for upcoming. Labels hide below 640px; the state is announced.
 */
export function ProgressStepper({ current, completed, className }: ProgressStepperProps) {
  const stateOf = (step: number): StepState =>
    step === current ? "current" : completed.has(step) ? "complete" : "upcoming";

  return (
    <nav aria-label={ar.stepper.label} className={className}>
      <ol className="flex items-center gap-2">
        {ar.stepper.steps.map((label, index) => {
          const step = index + 1;
          const state = stateOf(step);
          return (
            <Fragment key={label}>
              {index > 0 ? (
                <li
                  role="presentation"
                  aria-hidden
                  className={cx(
                    "h-0.5 min-w-3 flex-1 rounded-full",
                    stateOf(step - 1) === "complete" ? "bg-teal" : "bg-border",
                  )}
                />
              ) : null}
              <li
                data-state={state}
                aria-current={state === "current" ? "step" : undefined}
                className="flex shrink-0 items-center gap-2"
              >
                <span
                  className={cx(
                    "grid size-8 place-items-center rounded-full text-sm font-bold",
                    state === "complete" && "bg-teal text-white",
                    state === "current" &&
                      "bg-banana text-charcoal ring-4 ring-banana/40 motion-safe:animate-pulse",
                    state === "upcoming" && "border-2 border-border bg-white text-muted",
                  )}
                >
                  {state === "complete" ? <Icon name="check" className="size-4" /> : step}
                </span>
                <span
                  className={cx(
                    "hidden text-sm sm:inline",
                    state === "upcoming" ? "text-muted" : "font-bold text-charcoal",
                  )}
                >
                  {label}
                </span>
                <span className="sr-only">{ar.stepper.stepStatus[state]}</span>
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
