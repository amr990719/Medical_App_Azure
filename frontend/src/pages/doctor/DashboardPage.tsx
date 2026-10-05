import { useNavigate } from "react-router";
import { firstName, useSession } from "@/auth/useSession";
import { Button } from "@/components/ui/Button";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApplicationCard } from "@/features/applications/ApplicationCard";
import { hasActiveApplication, useApplications } from "@/features/applications/useApplications";
import { statusLabel, useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";

function EmptyFormIllustration() {
  return (
    <svg viewBox="0 0 120 96" role="img" aria-label={ar.emptyIllustration} className="h-24 w-32">
      <rect x="22" y="6" width="76" height="86" fill="#fff" stroke="#1A1A2E" strokeWidth="1.5" />
      <rect x="30" y="14" width="18" height="22" fill="none" stroke="#1A1A2E" strokeWidth="1.5" />
      {[44, 56, 68, 80].map((y) => (
        <line key={y} x1="30" x2="90" y1={y} y2={y} stroke="#1A1A2E" strokeWidth="1.5" strokeDasharray="3 3" />
      ))}
      <rect x="56" y="16" width="34" height="6" rx="3" fill="#F5E642" />
    </svg>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useSession();
  const reference = useReferenceData();
  const applications = useApplications();

  const name = firstName(user);
  const greeting = name ? t(ar.dashboard.greeting, { name }) : ar.dashboard.greetingFallback;
  const fiscalYear = reference.data?.fiscalYear;
  const list = applications.data?.results ?? [];
  const activeExists = fiscalYear !== undefined && hasActiveApplication(list, fiscalYear);
  const startNew = () => navigate("/application/new");

  const loadError = applications.error ?? reference.error;
  const isLoading = applications.isPending || reference.isPending;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-extrabold text-charcoal sm:text-3xl">{greeting}</h1>

      <section aria-labelledby="my-applications" className="mt-8">
        <h2 id="my-applications" className="text-lg font-extrabold text-charcoal">
          {ar.dashboard.myApplications}
        </h2>

        {loadError ? (
          <FullPageStatus
            isError
            message={loadError.message}
            onRetry={() => {
              void applications.refetch();
              void reference.refetch();
            }}
          />
        ) : isLoading ? (
          <div aria-busy="true" className="mt-4 space-y-3">
            {[0, 1].map((key) => (
              <div key={key} className="rounded-xl border border-border bg-white p-5">
                <Skeleton className="h-6 w-48" />
                <Skeleton className="mt-3 h-4 w-32" />
              </div>
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="mt-4 flex flex-col items-center rounded-xl border border-dashed border-border-hover bg-white px-6 py-10 text-center">
            <EmptyFormIllustration />
            <p className="mt-4 text-lg font-bold text-charcoal">{ar.dashboard.empty}</p>
            <p className="mt-1 max-w-[50ch] text-slate">
              {t(ar.dashboard.emptyHint, { year: fiscalYear ?? "" })}
            </p>
            <Button size="lg" className="mt-6" onClick={startNew}>
              <Icon name="plus" />
              {ar.dashboard.newApplication}
            </Button>
          </div>
        ) : (
          <>
            <ul className="mt-4 space-y-3">
              {list.map((application) => (
                <li key={application.id}>
                  <ApplicationCard
                    application={application}
                    statusLabel={statusLabel(reference.data, application.status)}
                  />
                </li>
              ))}
            </ul>
            <div className="mt-6 flex flex-col items-start gap-2">
              <Button
                size="lg"
                onClick={startNew}
                disabled={activeExists}
                aria-describedby={activeExists ? "active-application-hint" : undefined}
              >
                <Icon name="plus" />
                {ar.dashboard.newApplication}
              </Button>
              {activeExists ? (
                <p id="active-application-hint" className="text-sm text-slate">
                  {t(ar.dashboard.activeExists, { year: fiscalYear })}
                </p>
              ) : null}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
