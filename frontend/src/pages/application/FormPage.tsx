import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import type { WizardStep } from "@/components/form/ProgressStepper";
import { StickyActionBar } from "@/components/form/StickyActionBar";
import { ValidationErrorPanel, type PanelError } from "@/components/form/ValidationErrorPanel";
import { Button } from "@/components/ui/Button";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { useSignOut } from "@/auth/useSignOut";
import { ApplicationFormProvider } from "@/features/application-form/ApplicationFormProvider";
import { AutosaveIndicator } from "@/features/application-form/AutosaveIndicator";
import { useApplicationForm } from "@/features/application-form/context";
import { buildInlineErrors, InlineErrorsContext, NO_INLINE_ERRORS } from "@/features/application-form/inlineErrors";
import { PaperForm } from "@/features/application-form/PaperForm";
import { completedSteps, useFreshValidation, useValidation } from "@/features/applications/useValidation";
import { DocumentsChecklist } from "@/features/documents/DocumentsChecklist";
import { FeeSummaryPanel } from "@/features/fees/FeeSummaryPanel";
import { useFeeQuote } from "@/features/fees/useFeeQuote";
import { ar, t } from "@/i18n/ar";
import { WizardFrame } from "@/layouts/WizardFrame";

/** Steps 1–3 must pass before the receipt page (PROMPT.md §9.1). */
const FORM_STEPS = 3;

function FormScreen({ applicationId }: { applicationId: string }) {
  const draft = useApplicationForm();
  const navigate = useNavigate();
  const signOut = useSignOut();
  const validation = useValidation(applicationId);
  const freshValidation = useFreshValidation(applicationId);
  const fees = useFeeQuote(applicationId);
  const [showValidation, setShowValidation] = useState(false);
  const [checking, setChecking] = useState(false);
  const [blocker, setBlocker] = useState<string | null>(null);

  if (draft.loadError) {
    return <FullPageStatus isError message={draft.loadError.message} onRetry={draft.reload} />;
  }
  if (draft.isLoading || !draft.state || !draft.application) {
    return <FullPageStatus message={ar.common.loading} />;
  }

  const app = draft.application;
  const completed = completedSteps(validation.data?.stepsComplete);
  const firstOpen = ([1, 2, 3] as const).find((step) => !completed.has(step));
  const step: WizardStep = firstOpen ?? 3;
  const issues = showValidation ? (validation.data?.errors ?? []) : [];
  const panelErrors: PanelError[] = [
    ...(blocker ? [{ message: blocker }] : []),
    ...issues.filter((issue) => issue.step <= FORM_STEPS).map(({ message, field }) => ({ message, field })),
  ];
  const inline = showValidation ? buildInlineErrors(issues) : NO_INLINE_ERRORS;

  const onContinue = async () => {
    setChecking(true);
    setBlocker(null);
    try {
      const saved = await draft.flush();
      const result = await freshValidation();
      const blocking = result.errors.filter((issue) => issue.step <= FORM_STEPS);
      if (saved && blocking.length === 0) {
        navigate(`/application/${applicationId}/payment`);
        return;
      }
      if (!saved) setBlocker(ar.form.saveFailed);
      setShowValidation(true);
    } catch (error) {
      setBlocker(error instanceof Error ? error.message : ar.errors.unexpected);
      setShowValidation(true);
    } finally {
      setChecking(false);
    }
  };

  const goPrint = async () => {
    await draft.flush();
    navigate(`/application/${applicationId}/print`);
  };

  return (
    <WizardFrame
      applicationId={applicationId}
      fiscalYear={app.fiscalYear}
      step={step}
      completed={completed}
      beforeLeave={draft.flush}
      status={draft.readOnly ? null : <AutosaveIndicator status={draft.saveStatus} onRetry={draft.retrySave} />}
    >
      <InlineErrorsContext.Provider value={inline}>
        <div className="mx-auto max-w-[900px] space-y-5 px-3 pb-36 pt-5 sm:px-4">
          {draft.readOnly ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-status-submitted-fg/20 bg-status-submitted-bg p-4">
              <p className="font-bold text-status-submitted-fg">{ar.form.readOnly}</p>
              <Link to={`/application/${applicationId}/status`} className={buttonClasses("outline")}>
                {ar.form.readOnlyAction}
              </Link>
            </div>
          ) : null}
          {app.status === "NEEDS_CORRECTION" && app.reviewNotes ? (
            <div className="rounded-xl border-s-4 border-status-correction-fg bg-status-correction-bg p-4">
              <p className="font-extrabold text-status-correction-fg">{ar.form.correctionTitle}</p>
              <p className="mt-1 whitespace-pre-line text-charcoal" dir="auto">
                {app.reviewNotes}
              </p>
            </div>
          ) : null}

          <ValidationErrorPanel errors={panelErrors} />
          <PaperForm mode="edit" />
          <DocumentsChecklist />
          <FeeSummaryPanel
            quote={fees.data}
            isLoading={fees.isLoading}
            error={fees.error}
            title={t(ar.form.feesTitle, { year: app.fiscalYear })}
            accent="teal"
          />
        </div>
      </InlineErrorsContext.Provider>

      <StickyActionBar
        label={ar.form.actionsLabel}
        start={
          <Button
            variant="ghost"
            disabled={signOut.isPending}
            onClick={async () => {
              await draft.flush();
              signOut.mutate();
            }}
          >
            {ar.auth.signOut}
          </Button>
        }
        end={
          <>
            <Button variant="outline" onClick={() => void goPrint()}>
              <Icon name="print" className="size-4" />
              {ar.actions.print}
            </Button>
            {!draft.readOnly ? (
              <Button onClick={() => void onContinue()} disabled={checking} aria-busy={checking || undefined}>
                {checking ? ar.form.validating : ar.actions.continueToReceipt}
                <Icon name="arrow" mirror className="size-4" />
              </Button>
            ) : null}
          </>
        }
      />
    </WizardFrame>
  );
}

/** `/application/:id/form` — the paper-form replica, wizard steps 1–3 (PROMPT.md §9). */
export function FormPage() {
  const { id = "" } = useParams();
  return (
    <ApplicationFormProvider key={id} applicationId={id}>
      <FormScreen applicationId={id} />
    </ApplicationFormProvider>
  );
}
