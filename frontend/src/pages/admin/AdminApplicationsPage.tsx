import { useSearchParams } from "react-router";
import type { AdminApplicationQuery } from "@/api/endpoints/admin";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApplicationsTable } from "@/features/admin/ApplicationsTable";
import { FiltersBar } from "@/features/admin/FiltersBar";
import { Pagination } from "@/features/admin/Pagination";
import { useAdminApplications } from "@/features/admin/queries";
import { SearchBox } from "@/features/admin/SearchBox";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { formatNumber } from "@/utils/format";

const QUERY_KEYS: (keyof AdminApplicationQuery)[] = [
  "search",
  "status",
  "payment_status",
  "fiscal_year",
  "governorate",
  "syndicate_type",
  "sub_syndicate",
  "submitted_from",
  "submitted_to",
  "ordering",
  "page",
];

/** The URL is the state: filters survive reloads, links from the dashboard and the back button. */
function readQuery(params: URLSearchParams): AdminApplicationQuery {
  const query: AdminApplicationQuery = {};
  for (const key of QUERY_KEYS) {
    const value = params.get(key);
    if (value) query[key] = value;
  }
  return query;
}

/** `/admin/applications` — server-side search, filters, ordering and pagination (§44, §45). */
export function AdminApplicationsPage() {
  const [params, setParams] = useSearchParams();
  const query = readQuery(params);
  const reference = useReferenceData();
  const list = useAdminApplications(query);
  const page = Number(query.page ?? "1") || 1;

  /** Any change other than the page itself starts again from page 1. */
  const update = (changes: Partial<AdminApplicationQuery>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-extrabold text-charcoal">{ar.admin.list.title}</h1>
        {list.data ? (
          <p className="text-sm font-semibold text-slate" aria-live="polite">
            {t(ar.admin.list.count, { count: formatNumber(list.data.count) })}
          </p>
        ) : null}
      </header>

      <SearchBox
        key={query.search ?? ""}
        initial={query.search ?? ""}
        placeholder={ar.admin.list.searchPlaceholder}
        onSearch={(search) => update({ search })}
      />
      <FiltersBar
        query={query}
        reference={reference.data}
        onChange={(key, value) => update({ [key]: value })}
        onClear={() => setParams(query.ordering ? { ordering: query.ordering } : {})}
      />

      {list.error ? (
        <FullPageStatus isError message={list.error.message} onRetry={() => void list.refetch()} />
      ) : !list.data ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((key) => (
            <Skeleton key={key} className="h-12 w-full" />
          ))}
        </div>
      ) : list.data.results.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border-hover bg-white p-8 text-center">
          <p className="font-bold text-charcoal">{ar.admin.list.empty}</p>
          <p className="mt-1 text-sm text-slate">{ar.admin.list.emptyHint}</p>
        </div>
      ) : (
        <div aria-busy={list.isFetching || undefined} className="space-y-3">
          <ApplicationsTable
            rows={list.data.results}
            reference={reference.data}
            ordering={query.ordering ?? ""}
            onSort={(ordering) => update({ ordering })}
          />
          <Pagination page={page} count={list.data.count} onChange={(next) => update({ page: next > 1 ? String(next) : "" })} />
        </div>
      )}
    </div>
  );
}
