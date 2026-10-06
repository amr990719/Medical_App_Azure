import { useId } from "react";
import type { FeeQuote } from "@/api/types";
import { Skeleton } from "@/components/ui/Skeleton";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { formatMoney } from "@/utils/format";

export interface FeeSummaryPanelProps {
  /** The server quote (GET /applications/{id}/fees/); this component never computes money. */
  quote?: FeeQuote;
  isLoading?: boolean;
  error?: Error | null;
  /** Defaults to `ملخص الرسوم`; the form page uses `ملخص الاشتراك — السنة المالية {FY}`. */
  title?: string;
  /** "teal": start border (form, review). "banana": banana header (payment page, §18). */
  accent?: "teal" | "banana";
  className?: string;
}

/** PROMPT.md §17.6: the server's breakdown, tier and total. */
export function FeeSummaryPanel({
  quote,
  isLoading = false,
  error,
  title = ar.fees.title,
  accent = "teal",
  className,
}: FeeSummaryPanelProps) {
  const titleId = useId();
  const failure = error?.message ?? (quote && !quote.isValid ? quote.errorMessage || ar.fees.unavailable : null);

  return (
    <section
      aria-labelledby={titleId}
      aria-busy={isLoading || undefined}
      className={cx(
        "overflow-hidden rounded-xl border border-border bg-white p-5",
        accent === "teal" && "border-s-4 border-s-teal",
        className,
      )}
    >
      <div
        className={cx(
          "flex flex-wrap items-center justify-between gap-3",
          accent === "banana" && "-mx-5 -mt-5 mb-1 bg-banana px-5 py-3",
        )}
      >
        <h2 id={titleId} className="text-lg font-extrabold text-charcoal">
          {title}
        </h2>
        {quote?.isValid && quote.tier !== null ? (
          <span
            className={cx(
              "rounded-full px-3 py-0.5 text-sm font-bold",
              accent === "banana" ? "bg-white/80 text-charcoal" : "bg-teal-light text-teal-deep",
            )}
          >
            {t(ar.fees.tier, { tier: quote.tier })}
          </span>
        ) : null}
      </div>

      {isLoading ? (
        <div className="mt-4 space-y-3">
          {[0, 1, 2].map((key) => (
            <div key={key} className="flex justify-between gap-4">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      ) : failure ? (
        <p role="alert" className="mt-4 rounded-lg bg-danger-light p-3 font-semibold text-danger">
          {failure}
        </p>
      ) : quote ? (
        <table className="mt-3 w-full text-start">
          <thead className="sr-only">
            <tr>
              <th scope="col">{ar.fees.item}</th>
              <th scope="col">{ar.fees.amount}</th>
            </tr>
          </thead>
          <tbody>
            {quote.breakdown.map((row, index) => (
              <tr key={`${row.label}-${index}`} className="border-b border-border last:border-0">
                <td className="py-2 pe-4 align-top">
                  {row.label}
                  {row.note ? <span className="block text-xs font-semibold text-status-correction-fg">{row.note}</span> : null}
                </td>
                <td className="py-2 text-end align-top font-semibold whitespace-nowrap">{formatMoney(row.fee)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-charcoal">
              <th scope="row" className="pt-3 text-start text-base font-extrabold">
                {ar.fees.total}
              </th>
              <td className="pt-3 text-end text-xl font-extrabold whitespace-nowrap text-teal-deep">
                {formatMoney(quote.total)}
              </td>
            </tr>
          </tfoot>
        </table>
      ) : null}
    </section>
  );
}
