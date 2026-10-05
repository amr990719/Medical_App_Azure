import { Navigate, useSearchParams } from "react-router";
import { loginUrl } from "@/api/endpoints/auth";
import { DevLoginPanel } from "@/auth/DevLoginPanel";
import { homeFor, useSession } from "@/auth/useSession";
import { buttonClasses } from "@/components/ui/buttonClasses";
import { FullPageStatus } from "@/components/ui/FullPageStatus";
import { Icon } from "@/components/ui/Icon";
import { ar } from "@/i18n/ar";
import { PaperSlip } from "./PaperSlip";

type CallbackError = keyof typeof ar.auth.callbackErrors;

function callbackErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return code in ar.auth.callbackErrors
    ? ar.auth.callbackErrors[code as CallbackError]
    : ar.auth.callbackErrors.AUTH_FAILED;
}

export function LandingPage() {
  const { user, isLoading } = useSession();
  const [params] = useSearchParams();
  const authError = callbackErrorMessage(params.get("auth_error"));

  if (isLoading) return <FullPageStatus message={ar.common.loading} />;
  if (user) return <Navigate to={homeFor(user.role)} replace />;

  // Registration, verification and password reset all live on the Entra External ID pages.
  const signIn = loginUrl("/dashboard");

  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-12 sm:px-6 md:grid-cols-[1.1fr_0.9fr] md:py-20">
        <div>
          <h1 className="text-balance text-3xl leading-[1.35] font-extrabold text-charcoal sm:text-[2.6rem]">
            {ar.landing.title}
          </h1>
          <p className="mt-5 max-w-[60ch] text-lg text-slate">{ar.landing.lead}</p>

          {authError ? (
            <p
              role="alert"
              className="mt-6 flex items-start gap-2 rounded-lg border border-s-4 border-danger/30 border-s-danger bg-danger-light p-3 font-semibold text-charcoal"
            >
              <Icon name="alert" className="mt-1 text-danger" />
              {authError}
            </p>
          ) : null}

          <div className="mt-8 flex flex-wrap gap-3">
            <a href={signIn} className={buttonClasses("primary", "lg")}>
              {ar.auth.signIn}
            </a>
            <a href={signIn} className={buttonClasses("outline", "lg")}>
              {ar.auth.createAccount}
            </a>
          </div>
          <p className="mt-4 max-w-[60ch] text-sm text-muted">{ar.auth.externalNote}</p>

          <div className="mt-8 max-w-xl">
            <DevLoginPanel />
          </div>
        </div>
        <PaperSlip />
      </section>

      <section aria-labelledby="steps-title" className="border-t border-border bg-white">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
          <h2 id="steps-title" className="text-xl font-extrabold text-charcoal">
            {ar.landing.stepsTitle}
          </h2>
          <ol className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
            {ar.landing.steps.map((step, index) => (
              <li key={step.title} className="flex gap-3 lg:flex-col">
                <span className="grid size-9 shrink-0 place-items-center rounded-full bg-banana font-extrabold text-charcoal">
                  {index + 1}
                </span>
                <div>
                  <h3 className="font-bold text-charcoal">{step.title}</h3>
                  <p className="mt-1 text-sm text-slate">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </>
  );
}
