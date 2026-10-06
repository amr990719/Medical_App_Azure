import { useId, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import type { AdminApplicationDetail, AdminBeneficiary, DocumentSummary, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ActionDialog } from "@/features/admin/ActionDialog";
import { AuditList } from "@/features/admin/AuditList";
import { DocumentViewer } from "@/features/admin/DocumentViewer";
import { choiceLabel, documentTypeLabel } from "@/features/admin/labels";
import { NotesPanel } from "@/features/admin/NotesPanel";
import { PaymentBadge } from "@/features/admin/PaymentBadge";
import { PaymentPanel } from "@/features/admin/PaymentPanel";
import { useAdminApplication, useTransition } from "@/features/admin/queries";
import { TransitionButtons } from "@/features/admin/TransitionButtons";
import { NOTES_REQUIRED, type AdminTarget } from "@/features/admin/transitions";
import { FeeSummaryPanel } from "@/features/fees/FeeSummaryPanel";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { formatDate } from "@/utils/format";

const D = ar.admin.detail;
const F = D.fields;

function Panel({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={`space-y-3 rounded-xl border border-border bg-white p-5 ${className ?? ""}`}>
      <h2 id={id} className="text-lg font-extrabold text-charcoal">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Fields({ items }: { items: [label: string, value: ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0">
          <dt className="text-xs font-bold text-muted">{label}</dt>
          <dd className="font-semibold break-words text-charcoal">{value === "" || value === null ? D.empty : value}</dd>
        </div>
      ))}
    </dl>
  );
}

const ltr = (value: string | number | null | undefined) =>
  value === null || value === undefined || value === "" ? "" : <bdi dir="ltr">{value}</bdi>;

function MemberPanel({
  app,
  reference,
  revealed,
  onToggleReveal,
  busy,
}: {
  app: AdminApplicationDetail;
  reference: ReferenceData | undefined;
  revealed: boolean;
  onToggleReveal: () => void;
  busy: boolean;
}) {
  const doctor = app.doctor;
  const nationalId = (revealed && doctor.nationalId) || doctor.maskedNationalId;
  return (
    <Panel title={D.member}>
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-smoke p-3">
        <div>
          <p className="text-xs font-bold text-muted">{D.nationalId}</p>
          <p className="font-mono text-lg font-bold text-charcoal">
            <bdi dir="ltr">{nationalId || D.empty}</bdi>
          </p>
        </div>
        <Button variant="ghost" onClick={onToggleReveal} disabled={busy} className="ms-auto border border-border bg-white">
          {revealed ? D.hideFullId : D.showFullId}
        </Button>
        <p className="w-full text-xs text-muted">{D.revealAudited}</p>
      </div>
      <Fields
        items={[
          [F.fullName, doctor.fullName],
          [F.email, ltr(doctor.email)],
          [F.phone, ltr(doctor.phoneNumber)],
          [F.dateOfBirth, formatDate(doctor.dateOfBirth)],
          [F.gender, choiceLabel(reference?.genders, doctor.gender)],
          [F.religion, choiceLabel(reference?.religions, doctor.religion)],
          [F.syndicateType, choiceLabel(reference?.syndicateTypes, doctor.syndicateType)],
          [F.subSyndicate, doctor.subSyndicate],
          [F.registrationNumber, ltr(doctor.syndicateRegistrationNumber)],
          [F.registrationYear, ltr(doctor.syndicateRegistrationYear)],
          [F.treatmentCard, ltr(doctor.treatmentCardNumber)],
          [F.governorate, doctor.governorate],
          [F.neighborhood, doctor.neighborhood],
          [F.address, doctor.address],
        ]}
      />
    </Panel>
  );
}

function DocumentButton({ document, label, onView }: { document: DocumentSummary; label: string; onView: () => void }) {
  return (
    <button
      type="button"
      onClick={onView}
      aria-label={t(D.view, { label })}
      className="inline-flex items-center gap-1 rounded-md border border-teal/30 bg-teal-light px-2 py-1 text-xs font-bold text-teal-deep hover:border-teal"
      data-document-id={document.id}
    >
      <Icon name="check" className="size-3.5" strokeWidth={2.5} />
      {label}
    </button>
  );
}

function BeneficiaryDocuments({
  beneficiary,
  reference,
  onView,
}: {
  beneficiary: AdminBeneficiary;
  reference: ReferenceData | undefined;
  onView: (document: DocumentSummary, label: string) => void;
}) {
  const listed = new Set(beneficiary.requiredDocuments.map((r) => r.type));
  const extra = beneficiary.documents.filter((doc) => !listed.has(doc.documentType));
  return (
    <div className="flex flex-wrap gap-1.5">
      {beneficiary.requiredDocuments.map((requirement) => {
        const document = beneficiary.documents.find((doc) => doc.documentType === requirement.type);
        if (document) {
          return (
            <DocumentButton
              key={requirement.type}
              document={document}
              label={requirement.label}
              onView={() => onView(document, requirement.label)}
            />
          );
        }
        if (!requirement.required) return null;
        return (
          <span key={requirement.type} className="rounded-md bg-danger-light px-2 py-1 text-xs font-bold text-danger">
            {t(D.missingDocument, { label: requirement.label })}
          </span>
        );
      })}
      {extra.map((document) => {
        const label = documentTypeLabel(reference, document.documentType);
        return <DocumentButton key={document.id} document={document} label={label} onView={() => onView(document, label)} />;
      })}
    </div>
  );
}

function BeneficiariesPanel({
  app,
  reference,
  revealed,
  onView,
}: {
  app: AdminApplicationDetail;
  reference: ReferenceData | undefined;
  revealed: boolean;
  onView: (document: DocumentSummary, label: string) => void;
}) {
  const C = D.beneficiaryColumns;
  const rows = app.beneficiaries.filter((b) => b.isActive || b.fullName || b.kinship);
  return (
    <Panel title={D.beneficiaries}>
      {rows.length === 0 ? (
        <p className="text-sm text-slate">{D.noBeneficiaries}</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label={D.beneficiaries} className="w-full min-w-[40rem] text-sm">
            <thead className="bg-smoke text-slate">
              <tr>
                {[C.row, C.name, C.kinship, C.birthYear, C.nationalId, C.documents].map((label) => (
                  <th key={label} scope="col" className="px-2.5 py-2 text-start font-bold whitespace-nowrap">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id} className="border-t border-border align-top">
                  <td className="px-2.5 py-2">{b.rowNumber}</td>
                  <td className="px-2.5 py-2 font-semibold text-charcoal">{b.fullName}</td>
                  <td className="px-2.5 py-2 whitespace-nowrap">{choiceLabel(reference?.kinships, b.kinship)}</td>
                  <td className="px-2.5 py-2">{ltr(b.birthYear)}</td>
                  <td className="px-2.5 py-2 font-mono whitespace-nowrap">
                    {ltr((revealed && b.nationalId) || b.maskedNationalId)}
                  </td>
                  <td className="px-2.5 py-2">
                    <BeneficiaryDocuments beneficiary={b} reference={reference} onView={onView} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

/**
 * `/admin/applications/:id` (PROMPT.md §44): member data with an audited "show full national
 * ID", beneficiaries and documents in a viewer, the fee SNAPSHOT, receipt confirm/reject,
 * duplicate warnings, the server's allowed transitions, review and internal notes, audit, print.
 */
export function AdminApplicationDetailPage() {
  const { id = "" } = useParams();
  const [revealed, setRevealed] = useState(false);
  const reference = useReferenceData();
  const query = useAdminApplication(id, revealed);
  const transition = useTransition(id);
  const [viewing, setViewing] = useState<{ document: DocumentSummary; label: string } | null>(null);
  const [target, setTarget] = useState<AdminTarget | null>(null);
  const [flash, setFlash] = useState("");

  if (query.error) {
    return <FullPageStatus isError message={query.error.message} onRetry={() => void query.refetch()} />;
  }
  const app = query.data;
  if (!app) return <FullPageStatus message={ar.common.loading} />;

  const statusLabel = (status: string) => choiceLabel(reference.data?.statuses, status);
  const view = (document: DocumentSummary, label?: string) =>
    setViewing({ document, label: label ?? documentTypeLabel(reference.data, document.documentType) });
  const memberDocuments = app.documents.filter((doc) => !doc.beneficiaryId && doc.documentType !== "PAYMENT_RECEIPT");
  const closeTransition = () => {
    setTarget(null);
    transition.reset();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-8 sm:px-6">
      <Link to="/admin/applications" className={buttonClasses("ghost")}>
        <Icon name="arrow" mirror className="size-4 rotate-180" />
        {D.back}
      </Link>

      <header className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-white p-5">
        <div className="space-y-2">
          <h1 className="text-2xl font-extrabold text-charcoal">
            {ar.pages.adminApplication} <bdi dir="ltr">{app.referenceNumber}</bdi>
          </h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate">
            <StatusBadge status={app.status} label={statusLabel(app.status)} />
            <PaymentBadge status={app.paymentStatus} label={choiceLabel(reference.data?.paymentStatuses, app.paymentStatus)} />
            {app.submittedAt ? <span>{t(D.submittedAt, { date: formatDate(app.submittedAt) })}</span> : null}
          </div>
        </div>
        <Link to={`/admin/applications/${id}/print`} className={buttonClasses("outline")}>
          <Icon name="print" className="size-4" />
          {D.print}
        </Link>
      </header>

      {flash ? (
        <p role="status" className="rounded-lg border border-teal/30 bg-teal-light px-4 py-3 font-semibold text-teal-deep">
          {flash}
        </p>
      ) : null}

      {app.beneficiaryWarnings.length > 0 ? (
        <div role="alert" className="rounded-xl border border-warning/40 bg-banana-light p-4">
          <p className="flex items-center gap-2 font-extrabold text-status-correction-fg">
            <Icon name="alert" className="size-5" />
            {D.warningsTitle}
          </p>
          <ul className="mt-2 list-disc space-y-1 ps-6 text-sm text-charcoal">
            {app.beneficiaryWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          <MemberPanel
            app={app}
            reference={reference.data}
            revealed={revealed}
            onToggleReveal={() => setRevealed((value) => !value)}
            busy={query.isFetching}
          />
          <Panel title={D.application}>
            <Fields
              items={[
                [F.fiscalYear, ltr(app.fiscalYear)],
                [F.applicationType, choiceLabel(reference.data?.applicationTypes, app.applicationType)],
                [F.workStatus, choiceLabel(reference.data?.workStatuses, app.workStatus)],
                [F.declarationName, app.declarationName],
                [F.declarationAcceptedAt, formatDate(app.declarationAcceptedAt)],
              ]}
            />
            <h3 className="pt-2 text-sm font-extrabold text-charcoal">{D.memberDocuments}</h3>
            <div className="flex flex-wrap gap-1.5">
              {memberDocuments.map((document) => {
                const label = documentTypeLabel(reference.data, document.documentType);
                return <DocumentButton key={document.id} document={document} label={label} onView={() => view(document, label)} />;
              })}
            </div>
          </Panel>
          <BeneficiariesPanel app={app} reference={reference.data} revealed={revealed} onView={view} />
          {app.feeSnapshot ? (
            <FeeSummaryPanel quote={app.feeSnapshot} title={D.fees} />
          ) : (
            <Panel title={D.fees}>
              <p className="text-sm text-slate">{D.noSnapshot}</p>
            </Panel>
          )}
        </div>

        <aside className="min-w-0 space-y-5">
          <Panel title={ar.admin.actions.title}>
            <TransitionButtons
              allowed={app.allowedTransitions}
              status={app.status}
              paymentStatus={app.paymentStatus}
              onSelect={setTarget}
              disabled={transition.isPending}
            />
          </Panel>
          <PaymentPanel application={app} reference={reference.data} onView={(doc) => view(doc)} onDone={setFlash} />
          <Panel title={D.reviewNotes}>
            {app.reviewNotes ? (
              <p className="whitespace-pre-line text-charcoal">{app.reviewNotes}</p>
            ) : (
              <p className="text-sm text-slate">{D.noReviewNotes}</p>
            )}
            {app.reviewedAt ? (
              <p className="text-xs text-muted">
                {t(D.reviewedBy, { who: app.reviewedByEmail ?? "", date: formatDate(app.reviewedAt) })}
              </p>
            ) : null}
          </Panel>
          <NotesPanel applicationId={id} />
          <AuditList applicationId={id} reference={reference.data} />
        </aside>
      </div>

      <DocumentViewer document={viewing?.document ?? null} label={viewing?.label ?? ""} onClose={() => setViewing(null)} />

      {target ? (
        <ActionDialog
          title={`${ar.admin.actions.labels[target]} — ${app.referenceNumber ?? ""}`}
          notesLabel={NOTES_REQUIRED.has(target) ? ar.admin.actions.notesRequired : ar.admin.actions.notesLabel}
          notesHint={ar.admin.actions.notesHint}
          notesRequired={NOTES_REQUIRED.has(target)}
          confirmVariant={target === "REJECTED" ? "danger" : "primary"}
          busy={transition.isPending}
          error={transition.error?.message ?? null}
          onClose={closeTransition}
          onConfirm={(reviewNotes) =>
            transition.mutate(
              { toStatus: target, reviewNotes },
              {
                onSuccess: (detail) => {
                  closeTransition();
                  setFlash(t(ar.admin.actions.done, { status: statusLabel(detail.status) }));
                },
              },
            )
          }
        />
      ) : null}
    </div>
  );
}
