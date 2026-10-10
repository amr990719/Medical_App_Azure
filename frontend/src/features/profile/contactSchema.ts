import { z } from "zod";
import { ar, t } from "@/i18n/ar";
import { normalizeDigits } from "@/utils/digits";

/**
 * Instant feedback for the profile's contact fields (UX only: PATCH /profile/ and the server's
 * submission rules stay authoritative). Mirrors apps/common/arabic.py::normalize_mobile and the
 * Doctor column lengths; an empty value is allowed because the profile is completed while drafting.
 */
const MOBILE_RE = /^(\+20|0020|0)?1[0125]\d{8}$/;

export function normalizeMobile(raw: string): string | null {
  const value = normalizeDigits(raw).replace(/[\s\-().]+/g, "");
  return MOBILE_RE.test(value) ? `0${value.slice(-10)}` : null;
}

const text = (max: number) => z.string().trim().max(max, t(ar.profile.errors.tooLong, { max }));

export const contactSchema = z.object({
  phoneNumber: z.string().transform((raw, ctx) => {
    if (raw.trim() === "") return "";
    const mobile = normalizeMobile(raw);
    if (mobile === null) {
      ctx.addIssue({ code: "custom", message: ar.profile.errors.mobileInvalid });
      return z.NEVER;
    }
    return mobile;
  }),
  governorate: z.string(),
  neighborhood: text(100),
  address: text(300),
});

export type ContactInput = z.input<typeof contactSchema>;
export type ContactValues = z.output<typeof contactSchema>;
export type ContactField = keyof ContactInput;

/** camelCase form field → snake_case API field (PATCH body and §46 `fields` keys). */
export const contactApiField: Record<ContactField, "phone_number" | "governorate" | "neighborhood" | "address"> = {
  phoneNumber: "phone_number",
  governorate: "governorate",
  neighborhood: "neighborhood",
  address: "address",
};
