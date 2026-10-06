import type { FeeKey } from "@/api/types";
import { ar, t } from "@/i18n/ar";

const L = ar.admin.fees;
export const FEE_KEYS: FeeKey[] = ["member", "spouse", "child", "grad_son", "parent"];
export const TIERS = ["1", "2", "3", "4"] as const;

/** "حتى 5 سنوات قيد" … from the schedule's own boundaries (they are schedule data, D13). */
export function tierRange(boundaries: readonly number[], index: number): string {
  const [a = 5, b = 10, c = 15] = boundaries;
  const edges = [a, b, c];
  if (index === 0) return t(L.tierRange.first, { to: a });
  if (index === 3) return t(L.tierRange.last, { from: c });
  return t(L.tierRange.middle, { from: (edges[index - 1] ?? 0) + 1, to: edges[index] ?? 0 });
}
