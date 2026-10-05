import type { ReactNode } from "react";

export interface StickyActionBarProps {
  label: string;
  /** Start side (right in RTL): secondary actions such as sign-out. */
  start?: ReactNode;
  /** End side (left in RTL): print and the primary "continue" action. */
  end?: ReactNode;
}

/** Fixed bottom action bar of the wizard pages (PROMPT.md §9.1). Pages add bottom padding for it. */
export function StickyActionBar({ label, start, end }: StickyActionBarProps) {
  return (
    <div
      role="toolbar"
      aria-label={label}
      className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-white/95 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur print:hidden"
    >
      <div className="mx-auto flex max-w-[900px] flex-wrap items-center justify-between gap-3 px-4">
        <div data-slot="start" className="flex items-center gap-2">
          {start}
        </div>
        <div data-slot="end" className="flex flex-wrap items-center gap-2">
          {end}
        </div>
      </div>
    </div>
  );
}
