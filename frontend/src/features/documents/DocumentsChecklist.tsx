import { useId, useRef, type ReactNode } from "react";
import type { DocumentRequirement, DocumentSummary } from "@/api/types";
import { Icon } from "@/components/ui/Icon";
import { useApplicationForm } from "@/features/application-form/context";
import { useInlineErrors } from "@/features/application-form/inlineErrors";
import { requirementsOf } from "@/features/beneficiaries/requirements";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { useUploadDocument } from "./useUploadDocument";

const C = ar.form.checklist;

function ChecklistItem({
  slot,
  document,
  beneficiaryId,
  error,
}: {
  slot: DocumentRequirement;
  document: DocumentSummary | undefined;
  beneficiaryId: string | null;
  error?: string;
}) {
  const { application, readOnly, documentsChanged } = useApplicationForm();
  const inputRef = useRef<HTMLInputElement>(null);
  const errorId = useId();
  const upload = useUploadDocument({
    applicationId: application?.id ?? "",
    documentType: slot.type,
    beneficiaryId,
    imagesOnly: slot.type === "PERSONAL_PHOTO",
    onUploaded: documentsChanged,
  });
  const actionLabel = t(document ? C.replace : C.upload, { label: slot.label });
  const state = document ? "attached" : slot.required ? "missing" : "optional";
  const message = upload.error ?? (state === "missing" ? error : undefined);

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <span className="min-w-0 flex-1 font-semibold text-charcoal">{slot.label}</span>
      <span
        data-state={state}
        className={cx(
          "rounded-full px-2.5 py-0.5 text-xs font-bold",
          state === "attached" && "bg-teal-light text-teal-deep",
          state === "missing" && "bg-danger-light text-danger",
          state === "optional" && "bg-smoke text-muted",
        )}
      >
        {state === "attached" ? C.attached : state === "missing" ? C.missing : C.optional}
      </span>
      {!readOnly ? (
        <>
          <input
            ref={inputRef}
            type="file"
            className="sr-only"
            tabIndex={-1}
            aria-label={actionLabel}
            accept={upload.accept}
            onChange={(event) => {
              upload.select(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <button
            type="button"
            aria-label={actionLabel}
            aria-describedby={message ? errorId : undefined}
            disabled={!upload.ready || upload.isPending}
            onClick={() => inputRef.current?.click()}
            className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-sm font-bold text-teal-deep hover:border-teal hover:bg-teal-light disabled:text-muted"
          >
            <Icon name="upload" className="size-4" />
            {upload.isPending
              ? t(ar.upload.uploading, { percent: upload.progress })
              : document
                ? ar.upload.replace
                : C.uploadShort}
          </button>
        </>
      ) : null}
      {message ? (
        <p id={errorId} role="alert" className="w-full text-sm font-semibold text-danger">
          {message}
        </p>
      ) : null}
    </li>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  const titleId = useId();
  return (
    <div role="group" aria-labelledby={titleId} className="rounded-xl border border-border bg-white px-4 py-2">
      <h3 id={titleId} className="border-b border-border py-1.5 font-extrabold text-charcoal">
        {title}
      </h3>
      <ul className="divide-y divide-border">{children}</ul>
    </div>
  );
}

/**
 * Step 3 (`#documents`, PROMPT.md §9.6): every document the server's rules require or allow for
 * the member and each active beneficiary, its status, and an upload/replace action.
 */
export function DocumentsChecklist() {
  const titleId = useId();
  const { application, reference, memberDocuments } = useApplicationForm();
  const inline = useInlineErrors();
  if (!application || !reference) return null;

  const kinshipLabel = (value: string) => reference.kinships.find((k) => k.value === value)?.label ?? value;
  const memberSlots = reference.documentRules.member.filter((slot) => slot.stage !== "submit");
  const active = application.beneficiaries.filter((b) => b.isActive);

  return (
    <section id="documents" aria-labelledby={titleId} className="scroll-mt-40 print:hidden">
      <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
        {C.title}
      </h2>
      <p className="mt-1 text-sm text-slate">{C.hint}</p>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <Group title={C.member}>
          {memberSlots.map((slot) => (
            <ChecklistItem
              key={slot.type}
              slot={slot}
              document={memberDocuments[slot.type]}
              beneficiaryId={null}
              error={inline.memberDocuments[slot.type]}
            />
          ))}
        </Group>
        {active.map((beneficiary) => (
          <Group
            key={beneficiary.id}
            title={t(C.beneficiary, { name: beneficiary.fullName, kinship: kinshipLabel(beneficiary.kinship) })}
          >
            {requirementsOf(beneficiary).map((slot) => (
              <ChecklistItem
                key={slot.type}
                slot={slot}
                document={beneficiary.documents.find((doc) => doc.documentType === slot.type)}
                beneficiaryId={beneficiary.id}
                error={inline.rowDocuments[beneficiary.rowNumber - 1]?.[slot.type]}
              />
            ))}
          </Group>
        ))}
      </div>
    </section>
  );
}
