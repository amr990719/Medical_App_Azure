import type { FeeKey, FeeSchedule, TierFees, TierKey } from "@/api/types";
import { ar, t } from "@/i18n/ar";
import { formatMoney, formatNumber } from "@/utils/format";

const L = ar.admin.fees;
export const FEE_KEYS: FeeKey[] = ["member", "spouse", "child", "grad_son", "parent"];
/** Tier 0 = registered in the schedule's own fiscal year. Legacy schedules define 1-4 only. */
export const TIERS: TierKey[] = ["0", "1", "2", "3", "4"];
/** The only amount that may be "not available" (null): never free, never zero. */
export const isNullableFee = (tier: TierKey, key: FeeKey) => tier === "0" && key === "grad_son";

/** The tiers this schedule defines, in order. */
export const tiersOf = (fees: TierFees): TierKey[] => TIERS.filter((tier) => fees[tier] !== undefined);

/** "سنة القيد هي سنة الاشتراك", "حتى 5 سنوات قيد" … from the schedule's own boundaries (D13). */
export function tierRange(boundaries: readonly number[], tier: TierKey, hasTierZero: boolean): string {
  const [a = 5, b = 10, c = 15] = boundaries;
  if (tier === "0") return L.tierRange.zero;
  if (tier === "1") return hasTierZero ? t(L.tierRange.middle, { from: 1, to: a }) : t(L.tierRange.first, { to: a });
  if (tier === "2") return t(L.tierRange.middle, { from: a + 1, to: b });
  if (tier === "3") return t(L.tierRange.middle, { from: b + 1, to: c });
  return t(L.tierRange.last, { from: c });
}

/** A tier amount for display: `null` is "غير متاح" (not eligible), never 0. */
export const feeCell = (amount: number | null | undefined) =>
  amount === null || amount === undefined ? L.notAvailable : formatNumber(amount);

/** The administrative-fee rule of a version, in words. */
export function adminFeeRule(schedule: FeeSchedule): string {
  if (schedule.adminFeeFormula === "FLAT") {
    return t(L.adminFeeFormulaFlat, {
      memberOnly: formatMoney(schedule.adminFeeMemberOnly ?? 0),
      withBeneficiaries: formatMoney(schedule.adminFeeWithBeneficiaries ?? 0),
    });
  }
  return t(L.adminFeeFormulaPerBeneficiary, {
    base: formatMoney(schedule.adminFeeBase ?? 0),
    per: formatMoney(schedule.adminFeePerBeneficiary ?? 0),
  });
}
