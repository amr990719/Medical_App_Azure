import { ar } from "@/i18n/ar";

export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-banana focus:px-4 focus:py-2 focus:font-bold"
    >
      {ar.app.skipToContent}
    </a>
  );
}
