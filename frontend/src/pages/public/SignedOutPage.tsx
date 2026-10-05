import { loginUrl } from "@/api/endpoints/auth";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";

export function SignedOutPage() {
  return (
    <section className="mx-auto flex max-w-xl flex-col items-center px-4 py-20 text-center">
      <span className="grid size-14 place-items-center rounded-full bg-teal-light text-teal-deep">
        <Icon name="check" className="size-7" strokeWidth={2.5} />
      </span>
      <h1 className="mt-5 text-2xl font-extrabold text-charcoal">{ar.auth.signedOutTitle}</h1>
      <p className="mt-3 text-slate">{ar.auth.signedOutBody}</p>
      <a href={loginUrl("/dashboard")} className={`${buttonClasses("primary", "lg")} mt-8`}>
        {ar.auth.signIn}
      </a>
    </section>
  );
}
