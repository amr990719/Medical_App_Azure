import { cx } from "@/utils/cx";

/** Grey placeholder block while data loads. Decorative: the container carries aria-busy. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      data-skeleton
      aria-hidden
      className={cx("block animate-pulse rounded-md bg-border/80", className)}
    />
  );
}
