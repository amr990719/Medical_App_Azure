import { Link } from "react-router";
import type { AdminStats } from "@/api/types";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdminStats } from "@/features/admin/queries";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { formatNumber } from "@/utils/format";

type Tile = {
  label: string;
  count: (stats: AdminStats) => number;
  to: string;
  accent: string;
};

const T = ar.admin.tiles;
const TILES: Tile[] = [
  { label: T.total, count: (s) => s.total, to: "/admin/applications", accent: "border-t-charcoal" },
  { label: T.submitted, count: (s) => s.byStatus.SUBMITTED ?? 0, to: "?status=SUBMITTED", accent: "border-t-banana-deep" },
  { label: T.underReview, count: (s) => s.byStatus.UNDER_REVIEW ?? 0, to: "?status=UNDER_REVIEW", accent: "border-t-status-review-fg" },
  { label: T.needsCorrection, count: (s) => s.byStatus.NEEDS_CORRECTION ?? 0, to: "?status=NEEDS_CORRECTION", accent: "border-t-status-correction-fg" },
  { label: T.approved, count: (s) => s.byStatus.APPROVED ?? 0, to: "?status=APPROVED", accent: "border-t-teal" },
  { label: T.rejected, count: (s) => s.byStatus.REJECTED ?? 0, to: "?status=REJECTED", accent: "border-t-danger" },
  { label: T.receiptsPending, count: (s) => s.receiptsPending, to: "?payment_status=PENDING_REVIEW", accent: "border-t-warning" },
];

const href = (to: string) => (to.startsWith("?") ? `/admin/applications${to}` : to);

/** `/admin/dashboard` — §44 tiles; each opens the applications list with that filter. */
export function AdminDashboardPage() {
  const stats = useAdminStats();

  if (stats.error) {
    return <FullPageStatus isError message={stats.error.message} onRetry={() => void stats.refetch()} />;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8 sm:px-6">
      <header>
        <h1 className="text-2xl font-extrabold text-charcoal">{ar.admin.welcome}</h1>
        {stats.data ? (
          <p className="mt-1 text-slate">{t(ar.admin.fiscalYear, { year: stats.data.fiscalYear })}</p>
        ) : null}
      </header>
      <ul aria-label={ar.admin.tilesLabel} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {TILES.map((tile, index) => (
          <li key={tile.label} className={cx(index === 0 && "col-span-2 sm:col-span-1")}>
            <Link
              to={href(tile.to)}
              className={cx(
                "flex h-full flex-col justify-between gap-3 rounded-xl border border-border border-t-4 bg-white p-4 transition-colors hover:border-border-hover hover:bg-smoke",
                tile.accent,
              )}
            >
              <span className="text-sm font-bold text-slate">{tile.label}</span>
              {stats.data ? (
                <span className="text-3xl font-extrabold text-charcoal tabular-nums">{formatNumber(tile.count(stats.data))}</span>
              ) : (
                <Skeleton className="h-9 w-16" />
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
