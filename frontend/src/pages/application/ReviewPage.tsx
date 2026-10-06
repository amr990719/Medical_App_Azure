import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { ApiError } from "@/api/client";
import { submitApplication, updateApplication } from "@/api/endpoints/applications";
import { queryKeys } from "@/api/keys";
import type { Application } from "@/api/types";
import { StickyActionBar } from "@/components/form/StickyActionBar";
import { ValidationErrorPanel, type PanelError } from "@/components/form/ValidationErrorPanel";
import { Button } from "@/components/ui/Button";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { ApplicationFormProvider } from "@/features/application-form/ApplicationFormProvider";
import { PaperForm } from "@/features/application-form/PaperForm";
import { useApplication } from "@/features/applications/useApplication";
import { completedSteps, useValidation } from "@/features/applications/useValidation";
import { FeeSummaryPanel } from "@/features/fees/FeeSummaryPanel";
import { useFeeQuote } from "@/features/fees/useFeeQuote";
import { ar, t } from "@/i18n/ar";
import { WizardFrame } from "@/layouts/WizardFrame";
import { cx } from "@/utils/cx";

const R = ar.review;

/**
 * `/application/:id/review` — step 5 (PROMPT.md §8, §9.7): the whole form read-only, the
 * server's validation, the explicit declaration acceptance (stored server-side) and submission.
 */
export function ReviewPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const checkboxId = useId();
  const application = useApplication(id);
  const validation = useValidation(id);
  const fees = useFeeQuote(id);
  // Optimistic tick: the box follows the click at once; a refused PATCH puts it back.
  const [ticked, setTicked] = useState<boolean | null>(null);

  const accept = useMutation({
    mutationFn: (accepted: boolean) => updateApplication(id, { declaration_accepted: accepted }),
    onError: () => setTicked(null),
    onSuccess: (app) => {
      queryClient.setQueryData<Application>(queryKeys.applications.detail(id), app);
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.validation(id) });
    },
  });
  const submit = useMutation({
    mutationFn: () => submitApplication(id),
    onSuccess: (app) => {
      queryClient.setQueryData<Application>(queryKeys.applications.detail(id), app);
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.list() });
      navigate(`/application/${id}/status`, { replace: true, state: { justSubmitted: true } });
    },
  });

  if (application.error) {
    return <FullPageStatus isError message={application.error.message} onRetry={() => void application.refetch()} />;
  }
  const app = application.data;
  if (!app) return <FullPageStatus message={ar.common.loading} />;
  if (!app.isEditable && !submit.isSuccess) return <Navigate to={`/application/${id}/status`} replace />;

  const serverErrors = validation.data?.errors ?? [];
  const submitErrors: PanelError[] =
    submit.error instanceof ApiError && submit.error.errors?.length
      ? submit.error.errors.map(({ message, field }) => ({ message, field }))
      : submit.error
        ? [{ message: submit.error.message }]
        : [];
  const panel: PanelError[] = submitErrors.length
    ? submitErrors
    : serverErrors.map(({ message, field }) => ({ message, field }));
  const completed = completedSteps(validation.data?.stepsComplete);
  const formReady = validation.isSuccess && serverErrors.length === 0;
  const receiptMissing = validation.isSuccess && !completed.has(4);
  const accepted = ticked ?? app.declarationAccepted;
  const canSubmit = formReady && accepted && app.declarationAccepted && !submit.isPending && !accept.isPending;
  const resubmission = app.status === "NEEDS_CORRECTION";

  return (
    <WizardFrame applicationId={id} fiscalYear={app.fiscalYear} step={5} completed={completed}>
      <div className="mx-auto max-w-[900px] space-y-5 px-3 pb-36 pt-5 sm:px-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-extrabold text-charcoal">{R.title}</h1>
          <div className="flex flex-wrap gap-2">
            <Link to={`/application/${id}/payment`} className={buttonClasses("ghost")}>
              <Icon name="arrow" mirror className="size-4 rotate-180" />
              {R.backToReceipt}
            </Link>
            <Link to={`/application/${id}/form`} className={buttonClasses("outline")}>
              {R.editForm}
            </Link>
          </div>
        </div>
        <p className="text-slate">{R.intro}</p>

        {validation.isLoading ? (
          <p role="status" className="text-slate">
            {R.checking}
          </p>
        ) : null}
        <ValidationErrorPanel errors={panel} />
        {panel.length > 0 ? (
          <Link to={`/application/${id}/form`} className={buttonClasses("outline")}>
            {R.goFix}
          </Link>
        ) : null}
        {receiptMissing ? (
          <p className="rounded-xl bg-banana-light p-3 font-semibold text-status-submitted-fg">
            {ar.payment.needReceipt}{" "}
            <Link to={`/application/${id}/payment`} className="underline underline-offset-4">
              {ar.payment.title}
            </Link>
          </p>
        ) : null}
        {formReady && !receiptMissing && submitErrors.length === 0 ? (
          <p className="flex items-center gap-2 rounded-xl bg-teal-light p-3 font-bold text-teal-deep">
            <Icon name="check" />
            {R.ready}
          </p>
        ) : null}

        <ApplicationFormProvider key={id} applicationId={id} readOnly>
          <PaperForm mode="review" />
        </ApplicationFormProvider>

        <FeeSummaryPanel
          quote={fees.data}
          isLoading={fees.isLoading}
          error={fees.error}
          title={t(ar.form.feesTitle, { year: app.fiscalYear })}
          accent="teal"
        />

        <div
          className={cx(
            "flex items-start gap-3 rounded-xl border-2 bg-white p-4",
            accepted ? "border-teal" : "border-banana-deep",
          )}
        >
          <input
            id={checkboxId}
            type="checkbox"
            className="mt-1.5 size-5 shrink-0 accent-teal-deep"
            checked={accepted}
            disabled={accept.isPending || submit.isPending}
            onChange={(event) => {
              setTicked(event.target.checked);
              accept.mutate(event.target.checked);
            }}
          />
          <label htmlFor={checkboxId} className="font-bold text-charcoal">
            {R.accept}
          </label>
        </div>
        {accept.isError ? (
          <p role="alert" className="font-semibold text-danger">
            {accept.error.message}
          </p>
        ) : null}
      </div>

      <StickyActionBar
        label={ar.form.actionsLabel}
        end={
          <Button size="lg" disabled={!canSubmit} aria-busy={submit.isPending || undefined} onClick={() => submit.mutate()}>
            {submit.isPending ? R.submitting : resubmission ? R.resubmit : R.submit}
          </Button>
        }
      />
    </WizardFrame>
  );
}
