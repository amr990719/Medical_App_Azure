import { useId, useState, type ReactNode } from "react";
import type { Kinship } from "@/api/types";
import { NidInput } from "@/components/form/NidInput";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Icon } from "@/components/ui/Icon";
import { useApplicationForm } from "@/features/application-form/context";
import { useInlineErrors } from "@/features/application-form/inlineErrors";
import type { BeneficiaryField, BeneficiaryRow } from "@/features/application-form/types";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { digitsOnly } from "@/utils/digits";
import { DocumentModal } from "./DocumentModal";
import { documentsComplete, memberRequirementsOf } from "./requirements";

const B = ar.form.beneficiaries;

const cellInput =
  "w-full min-w-0 bg-transparent px-1.5 py-1 font-semibold text-ink outline-none focus:bg-banana-light disabled:opacity-100";

type RowProps = {
  index: number;
  row: BeneficiaryRow;
  onKinship: (index: number, kinship: string) => void;
  onOpenDocuments: (index: number) => void;
};

/** One row's controls, shared by the table row and the mobile card. */
function useRowControls({ index, row, onKinship, onOpenDocuments }: RowProps) {
  const { reference, readOnly, updateBeneficiary, clearRow, rowServer, rowErrors } = useApplicationForm();
  const inline = useInlineErrors();
  const n = index + 1;
  const labelOf = (field: string) => t(B.fieldOfRow, { field, n });
  const errorOf = (field: BeneficiaryField) => rowErrors[index]?.[field] ?? inline.rows[index]?.[field];
  const server = rowServer(index);
  const complete = server ? documentsComplete(server) : false;
  const docsError = Object.values(inline.rowDocuments[index] ?? {})[0];
  const hasContent = Boolean(row.kinship || row.name || row.birthYear || row.nationalId);
  const birthYearErrorId = useId();
  const birthYearError = errorOf("birthYear");

  // Like the name: a select clips a long label (ابن/ابنة (18 سنة أو أقل)) on paper, so print a
  // wrapping copy of the label instead.
  const kinshipLabel = reference?.kinships.find((k) => k.value === row.kinship)?.label ?? "";
  const kinshipOptions = reference?.kinships ?? [];
  const kinship = (
    <>
      <select
        aria-label={labelOf(B.kinship)}
        value={row.kinship}
        disabled={readOnly}
        aria-invalid={errorOf("kinship") ? true : undefined}
        onChange={(event) => onKinship(index, event.target.value)}
        className={cx(cellInput, "cursor-pointer disabled:cursor-default print:hidden", row.kinship === "" && "text-muted")}
      >
        <option value="">{B.kinshipPlaceholder}</option>
        {kinshipOptions.map((k) => (
          <option key={k.value} value={k.value} className="text-charcoal">
            {k.label}
          </option>
        ))}
      </select>
      <span
        data-print-value
        aria-hidden
        className="hidden min-w-0 break-words px-1 py-1 font-semibold leading-snug text-ink print:block"
      >
        {kinshipLabel}
      </span>
    </>
  );
  // An input clips a long name without a trace on paper: print a wrapping copy instead.
  const name = (
    <>
      <input
        aria-label={labelOf(B.name)}
        value={row.name}
        readOnly={readOnly}
        dir="auto"
        maxLength={200}
        aria-invalid={errorOf("name") ? true : undefined}
        onChange={(event) => updateBeneficiary(index, "name", event.target.value)}
        className={cx(cellInput, "print:hidden")}
      />
      <span
        data-print-value
        aria-hidden
        dir="auto"
        className="hidden min-w-0 flex-1 break-words px-1.5 py-1 font-semibold leading-snug text-ink print:block"
      >
        {row.name}
      </span>
    </>
  );
  const birthYear = (
    <input
      aria-label={labelOf(B.birthYear)}
      value={row.birthYear}
      readOnly={readOnly}
      dir="ltr"
      inputMode="numeric"
      maxLength={4}
      aria-invalid={birthYearError ? true : undefined}
      aria-describedby={birthYearError ? birthYearErrorId : undefined}
      onChange={(event) => updateBeneficiary(index, "birthYear", digitsOnly(event.target.value).slice(0, 4))}
      className={cx(cellInput, "text-center tabular-nums")}
    />
  );
  const nationalId = (
    <NidInput
      label={labelOf(B.nationalId)}
      size="small"
      value={row.nationalId}
      readOnly={readOnly}
      onChange={(value) => updateBeneficiary(index, "nationalId", value)}
    />
  );
  const paperclip = row.kinship ? (
    <button
      type="button"
      data-state={complete ? "complete" : "missing"}
      aria-label={`${t(B.documents, { n })} — ${complete ? B.documentsComplete : B.documentsMissing}`}
      onClick={() => onOpenDocuments(index)}
      className={cx(
        "grid size-8 shrink-0 place-items-center rounded-md print:hidden",
        complete ? "bg-teal text-white" : "bg-smoke text-muted hover:text-charcoal",
        docsError && !complete && "text-danger ring-2 ring-danger/50",
      )}
    >
      <Icon name="paperclip" className="size-4" strokeWidth={complete ? 2.5 : 2} />
    </button>
  ) : null;
  const clear =
    hasContent && !readOnly ? (
      <button
        type="button"
        aria-label={t(B.clear, { n })}
        onClick={() => clearRow(index)}
        className="grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-danger-light hover:text-danger print:hidden"
      >
        <Icon name="close" className="size-4" />
      </button>
    ) : null;
  const errors: RowError[] = (["kinship", "name", "birthYear", "nationalId"] as const).flatMap((field) => {
    const message = errorOf(field);
    return message ? [{ field, message }] : [];
  });
  if (docsError && !complete) errors.push({ field: "documents", message: docsError });

  return { n, kinship, name, birthYear, birthYearErrorId, nationalId, paperclip, clear, errors };
}

type RowError = { field: BeneficiaryField | "documents"; message: string };

/** The row's errors; the birth-year message carries the id its input points to. */
function RowErrors({ errors, birthYearErrorId }: { errors: RowError[]; birthYearErrorId: string }) {
  if (errors.length === 0) return null;
  return (
    <ul className="space-y-0.5 px-1.5 pb-1 text-xs font-semibold text-danger">
      {errors.map(({ field, message }) => (
        <li key={`${field}-${message}`} id={field === "birthYear" ? birthYearErrorId : undefined}>
          {message}
        </li>
      ))}
    </ul>
  );
}

function TableRow(props: RowProps) {
  const c = useRowControls(props);
  const cell = "border-[1.5px] border-paper-line p-0 align-middle";
  return (
    <tr>
      <td className={cx(cell, "px-1 text-center")}>
        <div className="flex items-center justify-center gap-1">
          <span className="w-5 font-bold text-charcoal">{c.n}</span>
          {c.paperclip}
        </div>
      </td>
      <td className={cell}>{c.kinship}</td>
      <td className={cell}>
        <div className="flex items-center">
          {c.name}
          {c.clear}
        </div>
        <RowErrors errors={c.errors} birthYearErrorId={c.birthYearErrorId} />
      </td>
      <td className={cell}>{c.birthYear}</td>
      <td className={cx(cell, "px-1 py-1")}>{c.nationalId}</td>
    </tr>
  );
}

function CardField({ label, children, after }: { label: string; children: ReactNode; after?: ReactNode }) {
  return (
    <div data-card-field className="flex min-w-0 flex-col gap-0.5">
      <span aria-hidden className="text-sm font-bold text-charcoal">
        {label}
      </span>
      <div className="border-b-[1.5px] border-dashed border-paper-line">{children}</div>
      {after}
    </div>
  );
}

function Card(props: RowProps) {
  const c = useRowControls(props);
  return (
    <div
      role="group"
      aria-label={t(B.row, { n: c.n })}
      className="flex flex-col gap-3 border-[1.5px] border-paper-line bg-paper p-3"
    >
      <div className="flex items-center gap-2">
        <span className="grid size-8 place-items-center border-[1.5px] border-paper-line font-bold">{c.n}</span>
        <span className="flex-1 font-bold text-charcoal">{t(B.row, { n: c.n })}</span>
        {c.paperclip}
        {c.clear}
      </div>
      <CardField label={B.kinship}>{c.kinship}</CardField>
      <CardField label={B.name}>{c.name}</CardField>
      <CardField
        label={B.birthYear}
        after={
          <RowErrors errors={c.errors.filter((e) => e.field === "birthYear")} birthYearErrorId={c.birthYearErrorId} />
        }
      >
        {c.birthYear}
      </CardField>
      <div className="flex min-w-0 flex-col gap-1">
        <span aria-hidden className="text-sm font-bold text-charcoal">
          {B.nationalId}
        </span>
        {c.nationalId}
      </div>
      <RowErrors errors={c.errors.filter((e) => e.field !== "birthYear")} birthYearErrorId={c.birthYearErrorId} />
    </div>
  );
}

/**
 * `بيانات المستفيدين مع العضو الأصلى` (PROMPT.md §9.5): exactly `max_beneficiaries` paper rows,
 * a paperclip per row with a kinship (grey = missing, green = complete), confirmation before a
 * kinship change removes documents or a cleared row is deleted. Cards below 768px; print = table.
 */
export function BeneficiaryTable({ layout = "auto" }: { layout?: "auto" | "table" }) {
  const titleId = useId();
  const draft = useApplicationForm();
  const desktop = useMediaQuery("(min-width: 768px)");
  const [documentsFor, setDocumentsFor] = useState<number | null>(null);
  const [kinshipChange, setKinshipChange] = useState<{ index: number; kinship: string } | null>(null);
  const { state, application, reference, readOnly, rowServer, pendingDeletion, memberDocuments } = draft;
  if (!state || !application) return null;

  const onKinship = (index: number, kinship: string) => {
    const server = rowServer(index);
    if (server && server.documents.length > 0 && kinship !== state.beneficiaries[index]?.kinship) {
      setKinshipChange({ index, kinship });
    } else {
      draft.updateBeneficiary(index, "kinship", kinship);
    }
  };
  const onOpenDocuments = async (index: number) => {
    if (!state.beneficiaries[index]?.id) await draft.flush(); // the row needs a server id first
    setDocumentsFor(index);
  };
  const rowProps = (row: BeneficiaryRow, index: number): RowProps => ({
    index,
    row,
    onKinship,
    onOpenDocuments: (i) => void onOpenDocuments(i),
  });
  const modalBeneficiary = documentsFor === null ? undefined : rowServer(documentsFor);
  // Member-owned slots this beneficiary's kinship makes necessary (server rule + server list).
  const conditional = reference?.documentRules.memberConditional ?? {};
  const modalMemberSlots = modalBeneficiary
    ? memberRequirementsOf(application).filter(
        (slot) => {
          const kinship = conditional[slot.type]?.requiredWithKinship;
          return kinship !== undefined && kinship === modalBeneficiary.kinship;
        },
      )
    : [];
  const deletionName =
    pendingDeletion === null ? "" : (rowServer(pendingDeletion)?.fullName ?? ar.documents.unnamedBeneficiary);
  const asTable = layout === "table" || desktop;

  return (
    <section id="beneficiaries" aria-labelledby={titleId} className="scroll-mt-40">
      <h2
        id={titleId}
        className="mb-3 border-y-[1.5px] border-paper-line bg-[#eceef1] py-1.5 text-center text-base font-extrabold text-charcoal print:bg-[#eceef1]"
      >
        {B.title}
      </h2>
      {asTable ? (
        <div className="overflow-x-auto">
          <table aria-labelledby={titleId} className="w-full min-w-[46rem] table-fixed border-collapse bg-paper text-sm">
            <colgroup>
              <col className="w-16 print:w-9" />
              <col className="w-44 print:w-28" />
              <col />
              <col className="w-[4.5rem] print:w-14" />
              <col className="w-[21rem] print:w-[17rem]" />
            </colgroup>
            <thead>
              <tr className="bg-[#eceef1]">
                {[B.number, B.kinship, B.name, B.birthYear, B.nationalId].map((label) => (
                  <th
                    key={label}
                    scope="col"
                    className="border-[1.5px] border-paper-line px-2 py-1.5 text-center font-extrabold text-charcoal"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {state.beneficiaries.map((row, index) => (
                <TableRow key={index} {...rowProps(row, index)} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {state.beneficiaries.map((row, index) => (
            <Card key={index} {...rowProps(row, index)} />
          ))}
        </div>
      )}

      {modalBeneficiary && documentsFor !== null ? (
        <DocumentModal
          open
          applicationId={application.id}
          beneficiary={modalBeneficiary}
          readOnly={readOnly}
          onClose={() => setDocumentsFor(null)}
          onExtracted={(fields) => draft.applyOcrSuggestions(fields, documentsFor)}
          memberSlots={modalMemberSlots}
          memberDocuments={memberDocuments}
        />
      ) : null}

      <ConfirmDialog
        open={kinshipChange !== null}
        title={ar.form.confirm.kinshipTitle}
        body={ar.form.confirm.kinshipBody}
        confirmLabel={ar.form.confirm.kinshipConfirm}
        onCancel={() => setKinshipChange(null)}
        onConfirm={() => {
          if (kinshipChange) draft.updateBeneficiary(kinshipChange.index, "kinship", kinshipChange.kinship as Kinship);
          setKinshipChange(null);
        }}
      />
      <ConfirmDialog
        open={pendingDeletion !== null}
        title={ar.form.confirm.deleteTitle}
        body={t(ar.form.confirm.deleteBody, { name: deletionName })}
        confirmLabel={ar.form.confirm.deleteConfirm}
        onCancel={draft.cancelDeletion}
        onConfirm={() => void draft.confirmDeletion()}
      />
    </section>
  );
}
