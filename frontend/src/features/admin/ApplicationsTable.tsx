import { Link } from "react-router";
import type { AdminApplicationRow, ReferenceData } from "@/api/types";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { formatDate, formatMoney } from "@/utils/format";
import { choiceLabel } from "./labels";
import { PaymentBadge } from "./PaymentBadge";

const C = ar.admin.list.columns;

/** Columns of PROMPT.md §44; `sort` is the server's `ordering` field when sortable. */
const COLUMNS = [
  { key: "reference", label: C.reference, sort: "reference_number" },
  { key: "applicant", label: C.applicant },
  { key: "syndicate", label: C.syndicate },
  { key: "status", label: C.status, sort: "status" },
  { key: "payment", label: C.payment },
  { key: "submittedAt", label: C.submittedAt, sort: "submitted_at" },
  { key: "total", label: C.total, sort: "total" },
] as const;

function nextOrdering(current: string, field: string): string {
  if (current === field) return `-${field}`;
  return field;
}

function ariaSort(ordering: string, field: string | undefined) {
  if (!field) return undefined;
  if (ordering === field) return "ascending" as const;
  if (ordering === `-${field}`) return "descending" as const;
  return "none" as const;
}

export interface ApplicationsTableProps {
  rows: AdminApplicationRow[];
  reference: ReferenceData | undefined;
  ordering: string;
  onSort: (ordering: string) => void;
}

/** Table on tablets and desktops; one card per application on phones (D79: one layout at a time). */
export function ApplicationsTable({ rows, reference, ordering, onSort }: ApplicationsTableProps) {
  const wide = useMediaQuery("(min-width: 768px)");
  const status = (row: AdminApplicationRow) => (
    <StatusBadge status={row.status} label={choiceLabel(reference?.statuses, row.status)} />
  );
  const payment = (row: AdminApplicationRow) => (
    <PaymentBadge status={row.paymentStatus} label={choiceLabel(reference?.paymentStatuses, row.paymentStatus)} />
  );
  const referenceLink = (row: AdminApplicationRow) => (
    <Link to={`/admin/applications/${row.id}`} className="font-bold text-teal-deep underline-offset-4 hover:underline">
      <bdi dir="ltr">{row.referenceNumber ?? row.id.slice(0, 8)}</bdi>
    </Link>
  );

  if (!wide) {
    return (
      <ul aria-label={ar.admin.list.tableLabel} className="space-y-3">
        {rows.map((row) => (
          <li key={row.id} className="space-y-2 rounded-xl border border-border bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {referenceLink(row)}
              {status(row)}
            </div>
            <p className="font-semibold text-charcoal">{row.doctorName}</p>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate">
              <span>{choiceLabel(reference?.syndicateTypes, row.syndicateType)}</span>
              <span>{formatDate(row.submittedAt)}</span>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              {payment(row)}
              <span className="font-bold text-teal-deep">{row.total === null ? "" : formatMoney(row.total)}</span>
            </div>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-white">
      <table aria-label={ar.admin.list.tableLabel} className="w-full min-w-[52rem] text-sm">
        <thead className="bg-smoke text-slate">
          <tr>
            {COLUMNS.map((column) => {
              const field = "sort" in column ? column.sort : undefined;
              const sort = ariaSort(ordering, field);
              return (
                <th key={column.key} scope="col" aria-sort={sort} className="px-3 py-2.5 text-start font-bold whitespace-nowrap">
                  {field ? (
                    <button
                      type="button"
                      onClick={() => onSort(nextOrdering(ordering, field))}
                      aria-label={t(ar.admin.list.sortBy, { column: column.label })}
                      className="inline-flex items-center gap-1 rounded hover:text-charcoal"
                    >
                      {column.label}
                      <Icon
                        name="chevron"
                        className={cx(
                          "size-3.5 transition-transform",
                          sort === "ascending" ? "-rotate-90" : sort === "descending" ? "rotate-90" : "rotate-90 opacity-30",
                        )}
                      />
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-border hover:bg-banana-light/50">
              <td className="px-3 py-2.5 whitespace-nowrap">{referenceLink(row)}</td>
              <td className="px-3 py-2.5 font-semibold text-charcoal">{row.doctorName}</td>
              <td className="px-3 py-2.5">{choiceLabel(reference?.syndicateTypes, row.syndicateType)}</td>
              <td className="px-3 py-2.5">{status(row)}</td>
              <td className="px-3 py-2.5">{payment(row)}</td>
              <td className="px-3 py-2.5 whitespace-nowrap">{formatDate(row.submittedAt)}</td>
              <td className="px-3 py-2.5 font-bold whitespace-nowrap text-teal-deep">
                {row.total === null ? "" : formatMoney(row.total)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
