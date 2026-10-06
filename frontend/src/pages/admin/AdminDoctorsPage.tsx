import { Link, useSearchParams } from "react-router";
import type { AdminDoctorQuery } from "@/api/endpoints/admin";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Skeleton } from "@/components/ui/Skeleton";
import { choiceLabel } from "@/features/admin/labels";
import { Pagination } from "@/features/admin/Pagination";
import { useAdminDoctors } from "@/features/admin/queries";
import { SearchBox } from "@/features/admin/SearchBox";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { formatNumber } from "@/utils/format";

const L = ar.admin.doctors;
const C = L.columns;
const KEYS: (keyof AdminDoctorQuery)[] = ["search", "syndicate_type", "governorate", "page"];
const selectClass = "min-h-10 rounded-lg border border-border-hover bg-white px-2.5 text-sm focus:border-teal";

/** `/admin/doctors` — members with masked national IDs; server-side search and pagination. */
export function AdminDoctorsPage() {
  const [params, setParams] = useSearchParams();
  const query: AdminDoctorQuery = {};
  for (const key of KEYS) {
    const value = params.get(key);
    if (value) query[key] = value;
  }
  const reference = useReferenceData();
  const list = useAdminDoctors(query);
  const page = Number(query.page ?? "1") || 1;

  const update = (changes: Partial<AdminDoctorQuery>) => {
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
        <h1 className="text-2xl font-extrabold text-charcoal">{L.title}</h1>
        {list.data ? <p className="text-sm font-semibold text-slate">{t(L.count, { count: formatNumber(list.data.count) })}</p> : null}
      </header>
      <div className="flex flex-wrap gap-3">
        <SearchBox key={query.search ?? ""} initial={query.search ?? ""} placeholder={L.searchPlaceholder} onSearch={(search) => update({ search })} />
        <select
          aria-label={ar.admin.list.syndicateType}
          value={query.syndicate_type ?? ""}
          onChange={(event) => update({ syndicate_type: event.target.value })}
          className={selectClass}
        >
          <option value="">{`${ar.admin.list.syndicateType}: ${ar.admin.list.all}`}</option>
          {(reference.data?.syndicateTypes ?? []).map((choice) => (
            <option key={choice.value} value={choice.value}>
              {choice.label}
            </option>
          ))}
        </select>
        <select
          aria-label={ar.admin.list.governorate}
          value={query.governorate ?? ""}
          onChange={(event) => update({ governorate: event.target.value })}
          className={selectClass}
        >
          <option value="">{`${ar.admin.list.governorate}: ${ar.admin.list.all}`}</option>
          {(reference.data?.governorates ?? []).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {list.error ? (
        <FullPageStatus isError message={list.error.message} onRetry={() => void list.refetch()} />
      ) : !list.data ? (
        <Skeleton className="h-40 w-full" />
      ) : list.data.results.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border-hover bg-white p-8 text-center font-bold text-charcoal">{L.empty}</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border bg-white">
            <table aria-label={L.tableLabel} className="w-full min-w-[56rem] text-sm">
              <thead className="bg-smoke text-slate">
                <tr>
                  {[C.name, C.email, C.nationalId, C.syndicate, C.registrationNumber, C.governorate, C.phone, C.applications].map((label) => (
                    <th key={label} scope="col" className="px-3 py-2.5 text-start font-bold whitespace-nowrap">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.data.results.map((doctor) => (
                  <tr key={doctor.id} className="border-t border-border hover:bg-banana-light/50">
                    <td className="px-3 py-2.5">
                      <Link to={`/admin/doctors/${doctor.id}`} className="font-bold text-teal-deep underline-offset-4 hover:underline">
                        {doctor.fullName || L.unnamed}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5">
                      <bdi dir="ltr">{doctor.email}</bdi>
                    </td>
                    <td className="px-3 py-2.5 font-mono whitespace-nowrap">
                      <bdi dir="ltr">{doctor.maskedNationalId}</bdi>
                    </td>
                    <td className="px-3 py-2.5">
                      {choiceLabel(reference.data?.syndicateTypes, doctor.syndicateType)}
                      {doctor.subSyndicate ? <span className="block text-xs text-muted">{doctor.subSyndicate}</span> : null}
                    </td>
                    <td className="px-3 py-2.5">
                      <bdi dir="ltr">{doctor.syndicateRegistrationNumber}</bdi>
                    </td>
                    <td className="px-3 py-2.5">{doctor.governorate}</td>
                    <td className="px-3 py-2.5">
                      <bdi dir="ltr">{doctor.phoneNumber}</bdi>
                    </td>
                    <td className="px-3 py-2.5 text-center font-bold">{doctor.applicationsCount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} count={list.data.count} onChange={(next) => update({ page: next > 1 ? String(next) : "" })} />
        </>
      )}
    </div>
  );
}
