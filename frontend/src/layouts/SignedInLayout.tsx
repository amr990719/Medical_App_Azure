import { Link, NavLink, Outlet } from "react-router";
import { useSession } from "@/auth/useSession";
import { useSignOut } from "@/auth/useSignOut";
import { Icon } from "@/components/ui/Icon";
import { UnionMark } from "@/components/ui/UnionMark";
import { ar } from "@/i18n/ar";
import { cx } from "@/utils/cx";
import { SkipLink } from "./SkipLink";

export interface NavItem {
  to: string;
  label: string;
}

/**
 * Shared chrome of the doctor and admin areas: union mark, section navigation, the signed-in
 * name and sign-out. The admin variant uses a charcoal bar so the two contexts never look alike.
 */
export function SignedInLayout({
  home,
  nav,
  variant,
}: {
  home: string;
  nav: readonly NavItem[];
  variant: "doctor" | "admin";
}) {
  const { user } = useSession();
  const signOut = useSignOut();
  const dark = variant === "admin";

  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header
        className={cx(
          "sticky top-0 z-40 border-b print:hidden",
          dark ? "border-charcoal bg-charcoal text-white" : "border-border bg-white/95 backdrop-blur",
        )}
      >
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6">
          <Link to={home} className="rounded-lg">
            <UnionMark inverted={dark} />
          </Link>
          <nav aria-label={ar.nav.main} className="order-last w-full sm:order-none sm:w-auto">
            <ul className="flex gap-1 overflow-x-auto">
              {nav.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end
                    className={({ isActive }) =>
                      cx(
                        "block whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-bold",
                        isActive
                          ? dark
                            ? "bg-banana text-charcoal"
                            : "bg-banana-light text-charcoal shadow-[inset_0_-2px_0_var(--color-banana-deep)]"
                          : dark
                            ? "text-white/75 hover:text-white"
                            : "text-slate hover:bg-smoke hover:text-charcoal",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="ms-auto flex items-center gap-2">
            {user ? (
              <span
                className={cx(
                  "hidden max-w-48 truncate text-sm font-semibold md:inline",
                  dark ? "text-white/80" : "text-slate",
                )}
              >
                {user.displayName || user.email}
              </span>
            ) : null}
            <button
              type="button"
              onClick={() => signOut.mutate()}
              disabled={signOut.isPending}
              className={cx(
                "inline-flex min-h-10 min-w-10 items-center justify-center gap-1.5 rounded-lg px-2.5 text-sm font-bold disabled:opacity-60",
                dark ? "text-white hover:bg-white/10" : "text-slate hover:bg-smoke hover:text-charcoal",
              )}
            >
              <Icon name="signOut" mirror className="size-4" />
              {/* Icon-only on phones so the bar keeps one row; the name stays for screen readers. */}
              <span className="sr-only sm:not-sr-only">{ar.auth.signOut}</span>
            </button>
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>
    </div>
  );
}
