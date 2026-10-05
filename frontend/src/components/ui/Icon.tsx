import type { SVGProps } from "react";
import { cx } from "@/utils/cx";

/**
 * Inline stroke icons (24×24). Paths are drawn for LTR; directional icons (arrows, chevrons,
 * sign-out) must be rendered with `mirror` so they flip in RTL. Never mirror check marks,
 * the logo, documents, printers or media icons (rtl-ui skill).
 */
const PATHS = {
  check: "M5 12.5l4.5 4.5L19 7.5",
  chevron: "M9 6l6 6-6 6",
  arrow: "M5 12h14M13 6l6 6-6 6",
  paperclip:
    "M20.5 11.5l-8.2 8.2a5.3 5.3 0 01-7.5-7.5l8.6-8.6a3.5 3.5 0 015 5l-8.6 8.6a1.8 1.8 0 01-2.5-2.5l7.9-7.9",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3",
  print: "M7 9V3h10v6M7 17H4v-6a2 2 0 012-2h12a2 2 0 012 2v6h-3M7 14h10v7H7z",
  signOut: "M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 16l4-4-4-4M14 12H3",
  plus: "M12 5v14M5 12h14",
  close: "M6 6l12 12M18 6L6 18",
  alert: "M12 8v5M12 16.5v.5M10.3 3.9L2.4 17.5A2 2 0 004.1 20.5h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  file: "M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5zM14 3v5h5",
  scan: "M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M4 12h16",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  clock: "M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z",
} as const;

export type IconName = keyof typeof PATHS;

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  /** Flip horizontally in RTL — only for directional icons. */
  mirror?: boolean;
  /** Accessible name; without it the icon is decorative (aria-hidden). */
  title?: string;
}

export function Icon({ name, mirror = false, title, className, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      data-icon={name}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      className={cx("size-5 shrink-0", mirror && "rtl:-scale-x-100", className)}
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
