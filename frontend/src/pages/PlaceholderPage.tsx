import { ar } from "@/i18n/ar";

/** Routes whose pages arrive in Sessions 5 and 6 (docs/plan.md). */
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <h1 className="text-2xl font-extrabold text-charcoal">{title}</h1>
      <p className="mt-3 rounded-lg border border-dashed border-border-hover bg-white p-4 text-slate">
        {ar.common.pageUnderConstruction}
      </p>
    </section>
  );
}
