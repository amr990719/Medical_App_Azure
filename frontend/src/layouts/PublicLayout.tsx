import { Link, Outlet } from "react-router";
import { UnionMark } from "@/components/ui/UnionMark";
import { ar } from "@/i18n/ar";
import { SkipLink } from "./SkipLink";

export function PublicLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-6xl items-center px-4 py-3 sm:px-6">
          <Link to="/" className="rounded-lg">
            <UnionMark />
          </Link>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>
      <footer className="border-t border-border bg-white">
        <p className="mx-auto max-w-6xl px-4 py-4 text-sm text-muted sm:px-6">
          {ar.app.union} — {ar.app.project}
        </p>
      </footer>
    </div>
  );
}
