import { Link } from "react-router";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { ar } from "@/i18n/ar";

export function NotFoundPage() {
  return (
    <section className="mx-auto flex max-w-xl flex-col items-center px-4 py-20 text-center">
      <h1 className="text-2xl font-extrabold text-charcoal">{ar.common.notFoundTitle}</h1>
      <p className="mt-3 text-slate">{ar.common.notFoundBody}</p>
      <Link to="/" className={`${buttonClasses("outline")} mt-6`}>
        {ar.common.backHome}
      </Link>
    </section>
  );
}
