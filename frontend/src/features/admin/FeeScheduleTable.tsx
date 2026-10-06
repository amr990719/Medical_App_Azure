import { useId } from "react";
import type { FeeSchedule } from "@/api/types";
import { ar, t } from "@/i18n/ar";
import { formatDate, formatMoney, formatNumber } from "@/utils/format";
import { FEE_KEYS, TIERS, tierRange } from "./feeSchedule";

const L = ar.admin.fees;

/** One schedule version, read-only: versions are immutable once created (PROMPT.md §17.1). */
export function FeeScheduleTable({ schedule }: { schedule: FeeSchedule }) {
  const settingsId = useId();
  const title = t(L.version, { year: schedule.fiscalYear, version: schedule.version });
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
            {TIERS.map((tier, index) => (
              <tr key={tier} className="border-t border-border">
                <th scope="row" className="px-3 py-2.5 text-start">
                  <span className="block font-bold text-charcoal">{t(L.tierN, { tier })}</span>
                  <span className="block text-xs font-normal text-muted">{tierRange(schedule.tierBoundaries, index)}</span>
                </th>
                {FEE_KEYS.map((key) => (
                  <td key={key} className="px-3 py-2.5 text-end font-semibold tabular-nums">
                    {formatNumber(schedule.tierFees[tier][key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <section aria-labelledby={settingsId} className="rounded-xl border border-border bg-white p-4">
        <h3 id={settingsId} className="mb-3 font-extrabold text-charcoal">
          {L.settings}
        </h3>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {(
            [
              [L.adminFeeMemberOnly, formatMoney(schedule.adminFeeMemberOnly ?? 0)],
              [L.adminFeeWithBeneficiaries, formatMoney(schedule.adminFeeWithBeneficiaries ?? 0)],
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
