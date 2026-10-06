import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { ar, t } from "@/i18n/ar";

/** The server's default page size (PROMPT.md §45: default 25, max 100). */
const PAGE_SIZE = 25;

function pageCount(count: number, pageSize = PAGE_SIZE): number {
  return Math.max(1, Math.ceil(count / pageSize));
}

export function Pagination({ page, count, onChange }: { page: number; count: number; onChange: (page: number) => void }) {
  const pages = pageCount(count);
  if (pages <= 1) return null;
  return (
    <nav aria-label={ar.admin.pagination.label} className="flex flex-wrap items-center justify-center gap-3 py-2">
      <Button variant="ghost" onClick={() => onChange(page - 1)} disabled={page <= 1}>
        <Icon name="chevron" mirror className="size-4 rotate-180" />
        {ar.admin.pagination.previous}
      </Button>
      <span className="text-sm font-semibold text-slate" aria-live="polite">
        {t(ar.admin.pagination.page, { page, pages })}
      </span>
      <Button variant="ghost" onClick={() => onChange(page + 1)} disabled={page >= pages}>
        {ar.admin.pagination.next}
        <Icon name="chevron" mirror className="size-4" />
      </Button>
    </nav>
  );
}
