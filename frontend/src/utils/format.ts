import { ar, t } from "@/i18n/ar";

/**
 * Display formatting with the ar-EG conventions of PROMPT.md §7.1:
 * money `3٬025 ج.م` (Western digits, Arabic thousands separator), dates `٣ أكتوبر ٢٠٢٦`.
 * Storage always stays Western digits and ISO dates.
 */
const ARABIC_THOUSANDS_SEPARATOR = "٬";
const CAIRO = "Africa/Cairo";
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

const westernNumber = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatNumber(value: number): string {
  return westernNumber.format(value).replace(/,/g, ARABIC_THOUSANDS_SEPARATOR);
}

export function formatMoney(value: number): string {
  return `${formatNumber(value)} ج.م`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ar-EG", {
    day: "numeric",
    month: "long",
    year: "numeric",
    // A calendar date has no time zone; a timestamp is shown in Egypt's local time.
    timeZone: DATE_ONLY.test(iso) ? "UTC" : CAIRO,
  }).format(date);
}

// Western digits, as in the dashboard example "آخر حفظ: منذ 5 دقائق" (PROMPT.md §43).
const relative = new Intl.RelativeTimeFormat("ar-EG-u-nu-latn", { numeric: "auto" });
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function formatRelativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return relative.format(0, "minute");
}

const MEGABYTE = 1024 * 1024;

/** `1.5 ميجابايت` / `200 كيلوبايت` for upload bars. */
export function formatFileSize(bytes: number): string {
  if (bytes >= MEGABYTE) {
    return t(ar.upload.megabytes, { value: Math.round((bytes / MEGABYTE) * 10) / 10 });
  }
  return t(ar.upload.kilobytes, { value: Math.max(1, Math.round(bytes / 1024)) });
}
