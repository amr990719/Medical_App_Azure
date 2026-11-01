import { normalizeDigits } from "@/utils/digits";

const ARABIC_DECIMAL_SEPARATOR = "٫";
const AMOUNT = /^\d{1,8}(?:\.\d{1,2})?$/;

/**
 * An amount typed by an admin (Western or Arabic digits, `.` or `٫`) as the decimal string sent
 * to the server, or null when it is not a positive amount with at most two decimals.
 * UX only: the server parses and checks it again; no float is ever involved.
 */
export function parseAmountInput(raw: string): string | null {
  const value = normalizeDigits(raw).trim().replace(ARABIC_DECIMAL_SEPARATOR, ".");
  if (!AMOUNT.test(value) || !/[1-9]/.test(value)) return null;
  return value;
}
