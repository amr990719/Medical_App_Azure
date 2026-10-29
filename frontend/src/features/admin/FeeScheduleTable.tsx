import { useId } from "react";
import type { FeeSchedule } from "@/api/types";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { formatDate, formatMoney } from "@/utils/format";
import { adminFeeRule, FEE_KEYS, feeCell, tierRange, TIERS } from "./feeSchedule";

const L = ar.admin.fees;

/** One schedule version, read-only: versions are immutable once created (PROMPT.md §17.1). */
export function FeeScheduleTable({ schedule }: { schedule: FeeSchedule }) {
  const settingsId = useId();
  const title = t(L.version, { year: schedule.fiscalYear, version: schedule.version });
  const hasUnavailable = TIERS.some((tier) => FEE_KEYS.some((key) => schedule.tierFees[tier][key] === null));
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-xl border border-border bg-white">
        <table aria-label={title} className="w-full min-w-[40rem] text-sm">
          <caption className="px-4 pt-3 text-start text-xs text-muted">{L.tableCaption}</caption>
          <thead className="bg-smoke text-slate">
            <tr>
              <th scope="col" className="px-3 py-2.5 text-start font-bold">
                {L.tier}
              </th>
              {FEE_KEYS.map((key) => (
                <th key={key} scope="col" className="px-3 py-2.5 text-end font-bold whitespace-nowrap">
                  {L.feeKeys[key]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TIERS.map((tier) => (
              <tr key={tier} className="border-t border-border">
                <th scope="row" className="px-3 py-2.5 text-start">
                  <span className="block font-bold text-charcoal">{t(L.tierN, { tier })}</span>
                  <span className="block text-xs font-normal text-muted">
                    {tierRange(schedule.tierBoundaries, tier)}
                  </span>
                </th>
                {FEE_KEYS.map((key) => {
                  const amount = schedule.tierFees[tier][key];
                  return (
                    <td
                      key={key}
                      data-unavailable={amount === null ? true : undefined}
                      className={cx(
                        "px-3 py-2.5 text-end font-semibold tabular-nums",
                        amount === null && "text-xs font-bold text-muted",
                      )}
                    >
                      {feeCell(amount)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {hasUnavailable ? <p className="px-4 pb-3 text-xs text-muted">{L.notAvailableHint}</p> : null}
      </div>
      <section aria-labelledby={settingsId} className="rounded-xl border border-border bg-white p-4">
        <h3 id={settingsId} className="mb-3 font-extrabold text-charcoal">
          {L.settings}
        </h3>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {(
            [
              [L.adminFeeFormula, adminFeeRule(schedule)],
              [L.serviceFee, formatMoney(schedule.serviceFee)],
              [L.ageCapThreshold, String(schedule.ageCapThreshold ?? "")],
              [L.ageCapAmount, formatMoney(schedule.ageCapAmount ?? 0)],
              [L.registrationYearMin, String(schedule.registrationYearMin ?? "")],
              [ar.admin.detail.fields.fiscalYear, String(schedule.fiscalYear)],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs font-bold text-muted">{label}</dt>
              <dd className="font-semibold text-charcoal">{value}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-xs text-muted">{t(L.createdAt, { date: formatDate(schedule.createdAt) })}</p>
      </section>
    </div>
  );
}
