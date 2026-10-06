import type { ApplicationStatus } from "@/api/types";
import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";

type StepState = "complete" | "current" | "upcoming";

const DECIDED = new Set<ApplicationStatus>(["APPROVED", "REJECTED", "NEEDS_CORRECTION"]);

function statesFor(status: ApplicationStatus): [StepState, StepState, StepState] {
  if (DECIDED.has(status)) return ["complete", "complete", "complete"];
  // Submitted and under review both wait on the reviewer: step 2 is the current one.
  if (status === "SUBMITTED" || status === "UNDER_REVIEW") return ["complete", "current", "upcoming"];
  return ["upcoming", "upcoming", "upcoming"];
}

function resultLabel(status: ApplicationStatus): string | null {
  if (status === "APPROVED") return ar.status.resultApproved;
  if (status === "REJECTED") return ar.status.resultRejected;
  if (status === "NEEDS_CORRECTION") return ar.status.resultCorrection;
  return null;
}

/** `تم التقديم ✓ → قيد المراجعة → إشعار بالنتيجة` (PROMPT.md §43). */
export function StatusTimeline({ status }: { status: ApplicationStatus }) {
  const states = statesFor(status);
  const result = resultLabel(status);

  return (
    <ol aria-label={ar.status.timelineLabel} className="flex flex-col gap-0 sm:flex-row sm:items-start">
      {ar.status.timeline.map((label, index) => {
        const state = states[index] ?? "upcoming";
        const last = index === ar.status.timeline.length - 1;
        return (
          <li key={label} data-state={state} className="relative flex flex-1 gap-3 pb-5 sm:flex-col sm:items-center sm:pb-0 sm:text-center">
            {!last ? (
              <span
                aria-hidden
                className={cx(
                  "absolute start-4 top-9 h-[calc(100%-2.25rem)] w-0.5 sm:start-[calc(50%+1.25rem)] sm:top-4 sm:h-0.5 sm:w-[calc(100%-2.5rem)]",
                  states[index + 1] === "upcoming" ? "bg-border" : "bg-teal",
                )}
              />
            ) : null}
            <span
              className={cx(
                "relative z-10 grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold",
                state === "complete" && "bg-teal text-white",
                state === "current" && "bg-banana text-charcoal ring-4 ring-banana/40 motion-safe:animate-pulse",
                state === "upcoming" && "border-2 border-border bg-white text-muted",
              )}
            >
              {state === "complete" ? <Icon name="check" className="size-4" /> : index + 1}
            </span>
            <span className="pt-1 sm:pt-2">
              <span className={cx("block font-bold", state === "upcoming" ? "text-muted" : "text-charcoal")}>
                {label}
              </span>
              {last && result ? <span className="block text-sm font-semibold text-slate">{result}</span> : null}
              <span className="sr-only">{ar.stepper.stepStatus[state]}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
