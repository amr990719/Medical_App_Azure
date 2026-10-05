import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { devLogin, fetchDevUsers } from "@/api/endpoints/auth";
import { queryKeys } from "@/api/keys";
import { ar, t } from "@/i18n/ar";
import { homeFor } from "./useSession";

/**
 * Development-only sign-in with the seeded users. Compiled out of production builds
 * (import.meta.env.DEV) and hidden whenever the backend answers 404 (DEV_AUTH_ENABLED off).
 */
export function DevLoginPanel() {
  if (!import.meta.env.DEV) return null;
  return <DevLoginList />;
}

function DevLoginList() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const users = useQuery({ queryKey: queryKeys.devUsers, queryFn: fetchDevUsers, retry: false });
  const login = useMutation({
    mutationFn: devLogin,
    onSuccess: (me) => {
      queryClient.setQueryData(queryKeys.me, me);
      navigate(homeFor(me.user.role), { replace: true });
    },
  });

  if (!users.data?.length) return null;

  return (
    <section
      aria-labelledby="dev-login-title"
      className="rounded-xl border-2 border-dashed border-warning/60 bg-banana-light/70 p-4"
    >
      <h2 id="dev-login-title" className="font-bold text-charcoal">
        {ar.auth.dev.title}
      </h2>
      <p className="text-sm text-slate">{ar.auth.dev.hint}</p>
      <ul className="mt-3 flex flex-col gap-2">
        {users.data.map((user) => (
          <li key={user.id}>
            <button
              type="button"
              disabled={login.isPending}
              onClick={() => login.mutate(user.email)}
              className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg border border-border bg-white px-3 py-2 text-start hover:border-border-hover disabled:opacity-60"
            >
              <span className="font-semibold">
                {t(ar.auth.dev.signInAs, { name: user.displayName })}
              </span>
              <span className="flex items-center gap-2 text-sm text-muted">
                <bdi dir="ltr">{user.email}</bdi>
                <span className="rounded bg-smoke px-2 py-0.5 text-xs font-bold text-slate">
                  {ar.auth.dev.roles[user.role]}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {login.error ? (
        <p role="alert" className="mt-2 text-sm font-semibold text-danger">
          {login.error.message}
        </p>
      ) : null}
    </section>
  );
}
