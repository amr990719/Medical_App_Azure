import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { choiceLabel } from "@/features/admin/labels";
import { PaymentBadge } from "@/features/admin/PaymentBadge";
import { useAdminDoctor } from "@/features/admin/queries";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar } from "@/i18n/ar";
import { formatDate, formatMoney } from "@/utils/format";

const L = ar.admin.doctors;
const F = ar.admin.detail.fields;

/** `/admin/doctors/:id` — profile (masked national ID) and the member's applications. */
export function AdminDoctorDetailPage() {
  const { id = "" } = useParams();
  const reference = useReferenceData();
  const query = useAdminDoctor(id);

  if (query.error) {
    return <FullPageStatus isError message={query.error.message} onRetry={() => void query.refetch()} />;
  }
  const doctor = query.data;
  if (!doctor) return <FullPageStatus message={ar.common.loading} />;

  const value = (text: string | number | null | undefined, ltr = false) =>
    text === null || text === undefined || text === "" ? ar.admin.detail.empty : ltr ? <bdi dir="ltr">{text}</bdi> : text;
  const fields: [string, ReactNode][] = [
    [ar.admin.detail.nationalId, value(doctor.maskedNationalId, true)],
    [F.email, value(doctor.email, true)],
    [F.phone, value(doctor.phoneNumber, true)],
    [F.dateOfBirth, value(formatDate(doctor.dateOfBirth))],
    [F.gender, value(choiceLabel(reference.data?.genders, doctor.gender))],
    [F.syndicateType, value(choiceLabel(reference.data?.syndicateTypes, doctor.syndicateType))],
    [F.subSyndicate, value(doctor.subSyndicate)],
    [F.registrationNumber, value(doctor.syndicateRegistrationNumber, true)],
    [F.registrationYear, value(doctor.syndicateRegistrationYear, true)],
    [F.governorate, value(doctor.governorate)],
    [F.address, value([doctor.neighborhood, doctor.address].filter(Boolean).join(" — "))],
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-5 px-4 py-8 sm:px-6">
      <Link to="/admin/doctors" className={buttonClasses("ghost")}>
        <Icon name="arrow" mirror className="size-4 rotate-180" />
        {L.back}
      </Link>
      <section className="space-y-4 rounded-xl border border-border bg-white p-5">
        <h1 className="text-2xl font-extrabold text-charcoal">{doctor.fullName || L.unnamed}</h1>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {fields.map(([label, content]) => (
            <div key={label} className="min-w-0">
              <dt className="text-xs font-bold text-muted">{label}</dt>
              <dd className="font-semibold break-words text-charcoal">{content}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-muted">{L.idNote}</p>
      </section>

      <section className="space-y-3 rounded-xl border border-border bg-white p-5">
        <h2 className="text-lg font-extrabold text-charcoal">{L.applications}</h2>
        {doctor.applications.length === 0 ? (
          <p className="text-sm text-slate">{L.noApplications}</p>
        ) : (
          <ul className="divide-y divide-border">
            {doctor.applications.map((app) => (
              <li key={app.id} className="flex flex-wrap items-center gap-3 py-3">
                <Link to={`/admin/applications/${app.id}`} className="font-bold text-teal-deep underline-offset-4 hover:underline">
                  <bdi dir="ltr">{app.referenceNumber ?? app.id.slice(0, 8)}</bdi>
                </Link>
                <StatusBadge status={app.status} label={choiceLabel(reference.data?.statuses, app.status)} />
                <PaymentBadge status={app.paymentStatus} label={choiceLabel(reference.data?.paymentStatuses, app.paymentStatus)} />
                <span className="text-sm text-slate">{formatDate(app.submittedAt)}</span>
                {app.total !== null ? <span className="ms-auto font-bold text-teal-deep">{formatMoney(app.total)}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
