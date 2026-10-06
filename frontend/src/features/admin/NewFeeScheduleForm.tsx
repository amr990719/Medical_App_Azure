import { useId, useState, type FormEvent } from "react";
import type { FeeKey, FeeSchedule, NewFeeSchedule, TierFees } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { digitsOnly, normalizeDigits } from "@/utils/digits";
import { FEE_KEYS, TIERS } from "./feeSchedule";

const L = ar.admin.fees;

type Values = Record<string, string>;

const tierField = (tier: string, key: FeeKey) => `tier.${tier}.${key}`;
const SCALARS = [
  ["adminFeeMemberOnly", L.adminFeeMemberOnly],
  ["adminFeeWithBeneficiaries", L.adminFeeWithBeneficiaries],
  ["ageCapThreshold", L.ageCapThreshold],
  ["ageCapAmount", L.ageCapAmount],
  ["registrationYearMin", L.registrationYearMin],
] as const;

function initialValues(base: FeeSchedule): Values {
  const values: Values = { fiscalYear: String(base.fiscalYear) };
  for (const tier of TIERS) for (const key of FEE_KEYS) values[tierField(tier, key)] = String(base.tierFees[tier][key]);
  base.tierBoundaries.forEach((edge, index) => (values[`boundary.${index}`] = String(edge)));
  for (const [name] of SCALARS) values[name] = String(base[name] ?? "");
  return values;
}

/** Non-negative integers only; Arabic digits accepted. The server re-validates everything. */
function parse(values: Values): { schedule?: NewFeeSchedule; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const number = (name: string) => {
    const raw = normalizeDigits(values[name] ?? "").trim();
    if (!/^\d+$/.test(raw)) {
      errors[name] = L.invalidNumber;
      return 0;
    }
    return Number(raw);
  };
  const tierFees = Object.fromEntries(
    TIERS.map((tier) => [tier, Object.fromEntries(FEE_KEYS.map((key) => [key, number(tierField(tier, key))]))]),
  ) as TierFees;
  const schedule: NewFeeSchedule = {
    fiscalYear: number("fiscalYear"),
    tierFees,
    tierBoundaries: [number("boundary.0"), number("boundary.1"), number("boundary.2")],
    adminFeeMemberOnly: number("adminFeeMemberOnly"),
    adminFeeWithBeneficiaries: number("adminFeeWithBeneficiaries"),
    ageCapThreshold: number("ageCapThreshold"),
    ageCapAmount: number("ageCapAmount"),
    registrationYearMin: number("registrationYearMin"),
  };
  return Object.keys(errors).length ? { errors } : { schedule, errors };
}

function NumberField({
  name,
  label,
  values,
  errors,
  onChange,
  compact = false,
}: {
  name: string;
  label: string;
  values: Values;
  errors: Record<string, string>;
  onChange: (name: string, value: string) => void;
  compact?: boolean;
}) {
  const id = useId();
  const error = errors[name];
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className={cx("text-xs font-bold text-slate", compact && "sr-only")}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        dir="ltr"
        value={values[name] ?? ""}
        onChange={(event) => onChange(name, digitsOnly(event.target.value))}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cx(
          "min-h-10 w-full min-w-16 rounded-lg border bg-white px-2 text-end text-sm tabular-nums focus:border-teal",
          error ? "border-danger" : "border-border-hover",
        )}
      />
      {error ? (
        <span id={`${id}-error`} className="text-xs font-semibold text-danger">
          {error}
        </span>
      ) : null}
    </div>
  );
}

/** New version form, prefilled from the schedule on screen. Submitting asks for confirmation. */
export function NewFeeScheduleForm({
  base,
  serverError,
  onSubmit,
  onCancel,
}: {
  base: FeeSchedule;
  serverError: string | null;
  onSubmit: (schedule: NewFeeSchedule) => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const [values, setValues] = useState(() => initialValues(base));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const change = (name: string, value: string) => {
    setValues((current) => ({ ...current, [name]: value }));
    setErrors((current) => ({ ...current, [name]: "" }));
  };
  const field = { values, errors, onChange: change };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const result = parse(values);
    setErrors(result.errors);
    if (result.schedule) onSubmit(result.schedule);
  };

  return (
    <form aria-labelledby={titleId} onSubmit={submit} noValidate className="space-y-4 rounded-xl border-2 border-banana-deep/50 bg-white p-5">
      <div>
        <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
          {L.newVersion}
        </h2>
        <p className="text-sm text-slate">{L.newHint}</p>
      </div>
      <div className="max-w-40">
        <NumberField name="fiscalYear" label={L.fiscalYear} {...field} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] text-sm">
          <thead className="text-slate">
            <tr>
              <th scope="col" className="px-1 py-2 text-start font-bold">
                {L.tier}
              </th>
              {FEE_KEYS.map((key) => (
                <th key={key} scope="col" className="px-1 py-2 text-end font-bold">
                  {L.feeKeys[key]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TIERS.map((tier) => (
              <tr key={tier}>
                <th scope="row" className="px-1 py-1.5 text-start font-bold whitespace-nowrap">
                  {t(L.tierN, { tier })}
                </th>
                {FEE_KEYS.map((key) => (
                  <td key={key} className="px-1 py-1.5 align-top">
                    <NumberField
                      name={tierField(tier, key)}
                      label={`${t(L.tierN, { tier })} — ${L.feeKeys[key]}`}
                      compact
                      {...field}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {SCALARS.map(([name, label]) => (
          <NumberField key={name} name={name} label={label} {...field} />
        ))}
        {[0, 1, 2].map((index) => (
          <NumberField key={index} name={`boundary.${index}`} label={t(L.boundary, { tier: index + 1 })} {...field} />
        ))}
      </div>
      {serverError ? (
        <p role="alert" className="rounded-lg bg-danger-light p-3 text-sm font-semibold text-danger">
          {serverError}
        </p>
      ) : null}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>
          {ar.common.cancel}
        </Button>
        <Button type="submit">{L.create}</Button>
      </div>
    </form>
  );
}
