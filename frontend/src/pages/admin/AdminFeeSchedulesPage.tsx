import { useState } from "react";
import type { NewFeeSchedule } from "@/api/types";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { Skeleton } from "@/components/ui/Skeleton";
import { FeeScheduleTable } from "@/features/admin/FeeScheduleTable";
import { NewFeeScheduleForm } from "@/features/admin/NewFeeScheduleForm";
import { useCreateFeeSchedule, useFeeSchedules } from "@/features/admin/queries";
import { useReferenceData } from "@/features/reference/useReferenceData";
import { ar, t } from "@/i18n/ar";
import { cx } from "@/utils/cx";

const L = ar.admin.fees;

/**
 * `/admin/fee-schedules` (PROMPT.md §17.1, §44): view any version (read-only), create a new
 * version for a fiscal year after confirmation. The server audits it (FEE_SCHEDULE_CHANGED) and
 * keeps every submitted application on the snapshot it was priced with.
 */
export function AdminFeeSchedulesPage() {
  const reference = useReferenceData();
  const schedules = useFeeSchedules();
  const create = useCreateFeeSchedule();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<NewFeeSchedule | null>(null);
  const [flash, setFlash] = useState("");

  if (schedules.error) {
    return <FullPageStatus isError message={schedules.error.message} onRetry={() => void schedules.refetch()} />;
  }
  const list = schedules.data ?? [];
  const fiscalYear = reference.data?.fiscalYear;
  const fallback = list.find((s) => s.isActive && s.fiscalYear === fiscalYear) ?? list.find((s) => s.isActive) ?? list[0];
  const shown = list.find((s) => s.id === selectedId) ?? fallback;

  const confirm = () => {
    if (!pending) return;
    create.mutate(pending, {
      onSuccess: (created) => {
        setPending(null);
        setCreating(false);
        setSelectedId(created.id);
        setFlash(t(L.created, { version: created.version, year: created.fiscalYear }));
      },
      onError: () => setPending(null),
    });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-4 py-8 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-extrabold text-charcoal">{L.title}</h1>
        <p className="max-w-3xl text-sm text-slate">{L.intro}</p>
      </header>

      {flash ? (
        <p role="status" className="rounded-lg border border-teal/30 bg-teal-light px-4 py-3 font-semibold text-teal-deep">
          {flash}
        </p>
      ) : null}

      {!schedules.data ? (
        <Skeleton className="h-64 w-full" />
      ) : shown ? (
        <div className="grid items-start gap-5 lg:grid-cols-[14rem_minmax(0,1fr)]">
          {list.length > 1 ? (
            <nav aria-label={L.versions} className="rounded-xl border border-border bg-white p-2">
              <ul className="space-y-1">
                {list.map((schedule) => (
                  <li key={schedule.id}>
                    <button
                      type="button"
                      aria-current={schedule.id === shown.id ? "true" : undefined}
                      onClick={() => setSelectedId(schedule.id)}
                      className={cx(
                        "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start text-sm font-semibold",
                        schedule.id === shown.id ? "bg-banana-light text-charcoal" : "text-slate hover:bg-smoke",
                      )}
                    >
                      <span
                        aria-hidden
                        className={cx("size-2 shrink-0 rounded-full", schedule.isActive ? "bg-teal" : "bg-border-hover")}
                      />
                      {t(L.version, { year: schedule.fiscalYear, version: schedule.version })}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}

          <section className={cx("min-w-0 space-y-4", list.length <= 1 && "lg:col-span-2")}>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-extrabold text-charcoal">
                {t(L.version, { year: shown.fiscalYear, version: shown.version })}
              </h2>
              <span
                className={cx(
                  "rounded-full px-2.5 py-0.5 text-xs font-bold",
                  shown.isActive ? "bg-teal-light text-teal-deep" : "bg-smoke text-slate",
                )}
              >
                {shown.isActive ? L.active : L.inactive}
              </span>
              {shown.lockedAt ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-charcoal px-2.5 py-0.5 text-xs font-bold text-white">
                  <Icon name="alert" className="size-3.5" />
                  {L.locked}
                </span>
              ) : null}
              <span className="text-xs text-muted">{L.readOnly}</span>
              {!creating ? (
                <Button className="ms-auto" onClick={() => setCreating(true)}>
                  <Icon name="plus" className="size-4" />
                  {L.newVersion}
                </Button>
              ) : null}
            </div>
            <FeeScheduleTable schedule={shown} />
            {creating ? (
              <NewFeeScheduleForm
                key={shown.id}
                base={shown}
                serverError={create.error?.message ?? null}
                onSubmit={setPending}
                onCancel={() => {
                  setCreating(false);
                  create.reset();
                }}
              />
            ) : null}
          </section>
        </div>
      ) : null}

      <ConfirmDialog
        open={pending !== null}
        title={L.confirmTitle}
        body={t(L.confirmBody, { year: pending?.fiscalYear ?? "" })}
        confirmLabel={L.create}
        busy={create.isPending}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
