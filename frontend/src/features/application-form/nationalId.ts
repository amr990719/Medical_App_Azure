import { digitsOnly } from "@/utils/digits";
import type { Gender } from "./types";

export type ParsedNationalId = { birthYear: number; gender: Gender };

/**
 * Instant-feedback mirror of backend/apps/reference/national_id.py (PROMPT.md §13 allows a UX
 * mirror): century digit, real birth date not in the future, position 13 odd = male.
 * The server re-parses and is the one that decides; this only pre-fills and warns early.
 */
export function parseNationalId(raw: string, today: Date = new Date()): ParsedNationalId | null {
  const value = digitsOnly(raw);
  if (value.length !== 14) return null;
  const century = value[0] === "2" ? 1900 : value[0] === "3" ? 2000 : null;
  if (century === null) return null;

  const year = century + Number(value.slice(1, 3));
  const month = Number(value.slice(3, 5));
  const day = Number(value.slice(5, 7));
  const date = new Date(Date.UTC(year, month - 1, day));
  const real = date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  if (!real || date.getTime() > today.getTime()) return null;

  return { birthYear: year, gender: Number(value[12]) % 2 === 1 ? "MALE" : "FEMALE" };
}
