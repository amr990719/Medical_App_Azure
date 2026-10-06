import { useSyncExternalStore } from "react";

/**
 * `true` while the media query matches. Without `matchMedia` (tests, very old browsers) it
 * answers `fallback`, so the desktop layout is the default.
 */
export function useMediaQuery(query: string, fallback = true): boolean {
  const supported = typeof window !== "undefined" && typeof window.matchMedia === "function";
  return useSyncExternalStore(
    (onChange) => {
      if (!supported) return () => {};
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => (supported ? window.matchMedia(query).matches : fallback),
    () => fallback,
  );
}
