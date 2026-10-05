/**
 * Eastern Arabic (٠-٩) and Persian (۰-۹) digits are accepted everywhere and normalized to
 * Western digits before validation and storage (PROMPT.md §7.1). Never silently dropped.
 */
const EASTERN_ARABIC_ZERO = 0x0660;
const PERSIAN_ZERO = 0x06f0;

export function normalizeDigits(value: string): string {
  return value.replace(/[٠-٩۰-۹]/g, (ch) => {
    const code = ch.charCodeAt(0);
    const zero = code >= PERSIAN_ZERO ? PERSIAN_ZERO : EASTERN_ARABIC_ZERO;
    return String(code - zero);
  });
}

/** Normalize, then keep only 0-9. */
export function digitsOnly(value: string): string {
  return normalizeDigits(value).replace(/\D/g, "");
}

export function toArabicDigits(value: string): string {
  return value.replace(/[0-9]/g, (d) => String.fromCharCode(EASTERN_ARABIC_ZERO + Number(d)));
}
