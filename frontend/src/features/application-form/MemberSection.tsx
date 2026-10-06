import { useId, type ReactNode } from "react";
import { BoxStringInput } from "@/components/form/BoxStringInput";
import { DashedField } from "@/components/form/DashedField";
import { DashedSelect } from "@/components/form/DashedSelect";
import { NidInput } from "@/components/form/NidInput";
import { RadioBoxGroup } from "@/components/form/RadioBoxGroup";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { normalizeDigits } from "@/utils/digits";
import { useApplicationForm } from "./context";
import { useMemberError } from "./inlineErrors";
import type { MemberField } from "./types";

const L = ar.form.member;

/** Column spans of the paper's 12-column rows (§9.4); one column below 768px. */
const SPAN = {
  3: "md:col-span-3",
  4: "md:col-span-4",
  5: "md:col-span-5",
  6: "md:col-span-6",
  8: "md:col-span-8",
  12: "md:col-span-12",
} as const;

function Cell({ span, children }: { span: keyof typeof SPAN; children: ReactNode }) {
  return <div className={cx("min-w-0", SPAN[span])}>{children}</div>;
}

/** Visible label + a box input that names itself (NidInput, BoxStringInput). */
function BoxRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 md:flex-row md:items-start md:gap-2">
      <span aria-hidden className="shrink-0 pt-1.5 font-bold text-charcoal">
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

/** The member field grid of the paper form, in the paper's order and grouping (PROMPT.md §9.4). */
export function MemberSection() {
  const titleId = useId();
  const { state, reference, readOnly, updateField } = useApplicationForm();
  const error = {
    syndicateType: useMemberError("syndicateType"),
    subSyndicate: useMemberError("subSyndicate"),
    registrationNumber: useMemberError("registrationNumber"),
    treatmentCardNumber: useMemberError("treatmentCardNumber"),
    syndicateRegistrationYear: useMemberError("syndicateRegistrationYear"),
    workStatus: useMemberError("workStatus"),
    memberName: useMemberError("memberName"),
    religion: useMemberError("religion"),
    nationalId: useMemberError("nationalId"),
    gender: useMemberError("gender"),
    birthYear: useMemberError("birthYear"),
    governorate: useMemberError("governorate"),
    neighborhood: useMemberError("neighborhood"),
    address: useMemberError("address"),
    mobile: useMemberError("mobile"),
  } satisfies Partial<Record<MemberField, string | undefined>>;

  if (!state || !reference) return null;
  const set = (field: MemberField) => (value: string) => updateField(field, value);
  const governorates = reference.governorates.map((name) => ({ value: name, label: name }));

  return (
    <section id="member" aria-labelledby={titleId} className="scroll-mt-40">
      <h2 id={titleId} className="sr-only">
        {L.section}
      </h2>
      <div data-testid="member-grid" className="grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-12">
        {/* Row 1 */}
        <Cell span={6}>
          <RadioBoxGroup
            label={L.syndicate}
            name="syndicateType"
            options={reference.syndicateTypes}
            value={state.syndicateType}
            onChange={set("syndicateType")}
            disabled={readOnly}
            error={error.syndicateType}
          />
        </Cell>
        <Cell span={3}>
          <DashedField
            label={L.subSyndicate}
            value={state.subSyndicate}
            onChange={set("subSyndicate")}
            maxLength={100}
            readOnly={readOnly}
            error={error.subSyndicate}
          />
        </Cell>
        <Cell span={3}>
          <DashedField
            label={L.registrationNumber}
            value={state.registrationNumber}
            onChange={set("registrationNumber")}
            numeric
            maxLength={20}
            readOnly={readOnly}
            error={error.registrationNumber}
          />
        </Cell>

        {/* Row 2 */}
        <Cell span={5}>
          <DashedField
            label={L.treatmentCard}
            value={state.treatmentCardNumber}
            onChange={set("treatmentCardNumber")}
            numeric
            maxLength={30}
            readOnly={readOnly}
            error={error.treatmentCardNumber}
          />
        </Cell>
        <Cell span={3}>
          <DashedField
            label={L.registrationYear}
            value={state.syndicateRegistrationYear}
            onChange={set("syndicateRegistrationYear")}
            numeric
            maxLength={4}
            readOnly={readOnly}
            error={error.syndicateRegistrationYear}
          />
        </Cell>
        <Cell span={4}>
          <RadioBoxGroup
            label={L.workStatus}
            name="workStatus"
            options={reference.workStatuses}
            value={state.workStatus}
            onChange={set("workStatus")}
            disabled={readOnly}
            error={error.workStatus}
          />
        </Cell>

        {/* Row 3 */}
        <Cell span={8}>
          <DashedField
            label={L.memberName}
            value={state.memberName}
            onChange={set("memberName")}
            maxLength={200}
            autoComplete="name"
            dir="auto"
            readOnly={readOnly}
            error={error.memberName}
          />
        </Cell>
        <Cell span={4}>
          <RadioBoxGroup
            label={L.religion}
            name="religion"
            options={reference.religions}
            value={state.religion}
            onChange={set("religion")}
            disabled={readOnly}
            error={error.religion}
          />
        </Cell>

        {/* Row 4 */}
        <Cell span={8}>
          <BoxRow label={L.nationalId}>
            <NidInput
              label={L.nationalId}
              name="nationalId"
              value={state.nationalId}
              onChange={set("nationalId")}
              readOnly={readOnly}
              error={error.nationalId}
            />
          </BoxRow>
        </Cell>
        <Cell span={4}>
          <RadioBoxGroup
            label={L.gender}
            name="gender"
            options={reference.genders}
            value={state.gender}
            onChange={set("gender")}
            disabled={readOnly}
            error={error.gender}
          />
        </Cell>

        {/* Row 5 */}
        <Cell span={5}>
          <DashedField
            label={L.birthYear}
            value={state.birthYear}
            onChange={set("birthYear")}
            numeric
            maxLength={4}
            readOnly={readOnly}
            error={error.birthYear}
          />
        </Cell>
        <Cell span={3}>
          <DashedSelect
            label={L.governorate}
            value={state.governorate}
            onChange={set("governorate")}
            options={governorates}
            placeholder={L.governoratePlaceholder}
            disabled={readOnly}
            error={error.governorate}
          />
        </Cell>
        <Cell span={4}>
          <DashedField
            label={L.neighborhood}
            value={state.neighborhood}
            onChange={set("neighborhood")}
            maxLength={100}
            readOnly={readOnly}
            error={error.neighborhood}
          />
        </Cell>

        {/* Row 6 */}
        <Cell span={8}>
          <DashedField
            label={L.address}
            value={state.address}
            onChange={set("address")}
            maxLength={300}
            autoComplete="street-address"
            readOnly={readOnly}
            error={error.address}
          />
        </Cell>
        <Cell span={4}>
          <DashedField
            label={L.mobile}
            value={state.mobile}
            onChange={(value) => updateField("mobile", normalizeDigits(value))}
            type="tel"
            dir="ltr"
            inputMode="tel"
            autoComplete="tel"
            maxLength={16}
            readOnly={readOnly}
            error={error.mobile}
          />
        </Cell>

        {/* Row 7 — from the Entra account, not editable here */}
        <Cell span={12}>
          <BoxRow label={L.email}>
            <BoxStringInput
              label={L.email}
              value={state.email}
              onChange={() => {}}
              length={Math.max(26, state.email.length)}
              size="small"
              readOnly
            />
          </BoxRow>
        </Cell>
      </div>
    </section>
  );
}
