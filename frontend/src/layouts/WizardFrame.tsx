import type { ReactNode } from "react";
import { Link } from "react-router";
import { useSignOut } from "@/auth/useSignOut";
import { ProgressStepper, type WizardStep } from "@/components/form/ProgressStepper";
import { Icon } from "@/components/ui/Icon";
import { ar, t } from "@/i18n/ar";
import { SkipLink } from "./SkipLink";

export interface WizardFrameProps {
  applicationId: string;
  fiscalYear: number | undefined;
  step: WizardStep;
  completed: ReadonlySet<number>;
  /** Autosave indicator on the form page. */
  status?: ReactNode;
  /** Runs before leaving (pending autosave), e.g. `flush`. */
  beforeLeave?: () => Promise<unknown>;
  children: ReactNode;
}

/**
 * Chrome of wizard steps 1–5 (PROMPT.md §9.1): sticky top bar with sign-out icon, the title
 * `استمارة اشتراك — {fy}`, print icon and autosave indicator, then the sticky ProgressStepper.
 */
export function WizardFrame({
  applicationId,
  fiscalYear,
  step,
  completed,
  status,
  beforeLeave,
  children,
}: WizardFrameProps) {
  const signOut = useSignOut();
  const iconButton =
    "grid size-10 shrink-0 place-items-center rounded-lg text-slate hover:bg-smoke hover:text-charcoal disabled:opacity-60";

  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header className="sticky top-0 z-40 border-b border-border bg-white/95 backdrop-blur print:hidden">
        <div className="mx-auto flex max-w-[900px] items-center gap-2 px-3 pt-2 sm:px-4">
          <button
            type="button"
            aria-label={ar.auth.signOut}
            disabled={signOut.isPending}
            onClick={async () => {
              await beforeLeave?.();
              signOut.mutate();
            }}
            className={iconButton}
          >
            <Icon name="signOut" mirror />
          </button>
          <p className="min-w-0 flex-1 truncate text-center text-base font-extrabold text-charcoal sm:text-lg">
            {fiscalYear ? t(ar.form.topTitle, { year: fiscalYear }) : ar.app.formTitle}
          </p>
          {status}
          <Link to={`/application/${applicationId}/print`} aria-label={ar.form.printForm} className={iconButton}>
            <Icon name="print" />
          </Link>
        </div>
        <div className="mx-auto max-w-[900px] px-3 pb-2.5 pt-1.5 sm:px-4">
          <ProgressStepper current={step} completed={completed} />
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
    </div>
  );
}
