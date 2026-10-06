import { useId, type ReactNode } from "react";
import type { AdminApplicationQuery } from "@/api/endpoints/admin";
import type { Choice, ReferenceData } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ar } from "@/i18n/ar";

type FilterKey = Exclude<keyof AdminApplicationQuery, "search" | "ordering" | "page">;

const L = ar.admin.list;
const fieldClass = "min-h-10 w-full rounded-lg border border-border-hover bg-white px-2.5 text-sm focus:border-teal";

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-bold text-slate">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

function SelectFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly Choice[];
  onChange: (value: string) => void;
}) {
  return (
    <Field label={label}>
      {(id) => (
        <select id={id} value={value} onChange={(event) => onChange(event.target.value)} className={fieldClass}>
          <option value="">{L.all}</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

/** Filters of PROMPT.md §24/§44; every choice list comes from reference data. */
export function FiltersBar({
  query,
  reference,
  onChange,
  onClear,
}: {
  query: AdminApplicationQuery;
  reference: ReferenceData | undefined;
  onChange: (key: FilterKey, value: string) => void;
  onClear: () => void;
}) {
  const fiscalYear = reference?.fiscalYear;
  const years = fiscalYear ? [fiscalYear, fiscalYear - 1].map((y) => ({ value: String(y), label: String(y) })) : [];
  const statuses = (reference?.statuses ?? []).filter((choice) => choice.value !== "DRAFT");
  const hasFilters = (Object.keys(query) as (keyof AdminApplicationQuery)[]).some(
    (key) => key !== "ordering" && key !== "page" && query[key],
  );

  return (
    <fieldset className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-white p-4 sm:grid-cols-3 lg:grid-cols-5">
      <legend className="sr-only">{L.filters}</legend>
      <SelectFilter label={L.status} value={query.status ?? ""} options={statuses} onChange={(v) => onChange("status", v)} />
      <SelectFilter
        label={L.paymentStatus}
        value={query.payment_status ?? ""}
        options={reference?.paymentStatuses ?? []}
        onChange={(v) => onChange("payment_status", v)}
      />
      <SelectFilter label={L.fiscalYear} value={query.fiscal_year ?? ""} options={years} onChange={(v) => onChange("fiscal_year", v)} />
      <SelectFilter
        label={L.governorate}
        value={query.governorate ?? ""}
        options={(reference?.governorates ?? []).map((g) => ({ value: g, label: g }))}
        onChange={(v) => onChange("governorate", v)}
      />
      <SelectFilter
        label={L.syndicateType}
        value={query.syndicate_type ?? ""}
        options={reference?.syndicateTypes ?? []}
        onChange={(v) => onChange("syndicate_type", v)}
      />
      <Field label={L.subSyndicate}>
        {(id) => (
          <input
            id={id}
            defaultValue={query.sub_syndicate ?? ""}
            onBlur={(event) => onChange("sub_syndicate", event.target.value.trim())}
            onKeyDown={(event) => {
              if (event.key === "Enter") onChange("sub_syndicate", event.currentTarget.value.trim());
            }}
            className={fieldClass}
          />
        )}
      </Field>
      <Field label={L.submittedFrom}>
        {(id) => (
          <input
            id={id}
            type="date"
            dir="ltr"
            value={query.submitted_from ?? ""}
            onChange={(event) => onChange("submitted_from", event.target.value)}
            className={fieldClass}
          />
        )}
      </Field>
      <Field label={L.submittedTo}>
        {(id) => (
          <input
            id={id}
            type="date"
            dir="ltr"
            value={query.submitted_to ?? ""}
            onChange={(event) => onChange("submitted_to", event.target.value)}
            className={fieldClass}
          />
        )}
      </Field>
      <div className="col-span-2 flex items-end sm:col-span-1">
        <Button variant="ghost" onClick={onClear} disabled={!hasFilters} className="w-full">
          {L.clear}
        </Button>
      </div>
    </fieldset>
  );
}
