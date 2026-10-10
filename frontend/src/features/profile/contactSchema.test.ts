import { describe, expect, it } from "vitest";
import { contactSchema } from "./contactSchema";

const valid = { phoneNumber: "01012345678", governorate: "القاهرة", neighborhood: "", address: "" };

describe("contactSchema", () => {
  it("accepts an empty profile (fields are completed while drafting)", () => {
    expect(contactSchema.safeParse({ phoneNumber: "", governorate: "", neighborhood: "", address: "" }).success).toBe(
      true,
    );
  });

  it.each(["01012345678", "+201012345678", "00201512345678", "010 1234 5678", "٠١٠١٢٣٤٥٦٧٨"])(
    "accepts the Egyptian mobile %s and stores it as 01XXXXXXXXX",
    (phoneNumber) => {
      const result = contactSchema.safeParse({ ...valid, phoneNumber });
      expect(result.success).toBe(true);
      expect(result.data?.phoneNumber).toMatch(/^01[0125]\d{8}$/);
    },
  );

  it.each(["0101234567", "01312345678", "02123456789", "abc"])("refuses %s", (phoneNumber) => {
    const result = contactSchema.safeParse({ ...valid, phoneNumber });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]?.message).toBe("رقم الهاتف المحمول غير صحيح");
  });

  it("limits the free-text lengths to the server's columns", () => {
    expect(contactSchema.safeParse({ ...valid, neighborhood: "ح".repeat(101) }).success).toBe(false);
    expect(contactSchema.safeParse({ ...valid, address: "ع".repeat(301) }).success).toBe(false);
    expect(contactSchema.safeParse({ ...valid, address: "ع".repeat(300) }).success).toBe(true);
  });

  it("trims free text", () => {
    expect(contactSchema.parse({ ...valid, address: "  شارع النصر  " }).address).toBe("شارع النصر");
  });
});
