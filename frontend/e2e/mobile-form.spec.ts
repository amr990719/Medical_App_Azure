import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createDraftApplication, fixture, pageDevLogin } from "./helpers";

/**
 * PROMPT.md §43 mobile layout on a real phone profile (Pixel 7 at 390 × 844: touch, mobile
 * viewport, device scale factor) — not a resized desktop page. The doctor finishes a draft on the
 * phone: adds a beneficiary in the card layout, attaches its document, uploads the receipt,
 * reviews and submits. No page of the journey may scroll horizontally.
 *
 * Artefacts: docs/screenshots/session-9/mobile-*.png
 */
const ARTEFACTS = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots/session-9");

async function expectNoHorizontalScroll(page: Page, name: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, `${name}: no horizontal scrolling at ${page.viewportSize()?.width}px`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: join(ARTEFACTS, `mobile-${name}.png`), fullPage: true });
}

const rowField = (page: Page, field: string, n: number) => page.getByLabel(`${field} — المستفيد رقم ${n}`, { exact: true });

test.setTimeout(180_000);

test("doctor completes and submits the form on a 390 × 844 phone", async ({ page, request }) => {
  test.skip(test.info().project.name !== "mobile", "mobile project only");
  mkdirSync(ARTEFACTS, { recursive: true });
  expect(page.viewportSize()).toEqual({ width: 390, height: 844 });

  // Member data and a WIFE row with documents already saved; receipt and declaration not yet.
  const draft = await createDraftApplication(request, {
    beneficiaries: [{ kinship: "WIFE", full_name: "منى سعيد عبد الله", birth_year: 1988 }],
    complete: false,
  });
  await pageDevLogin(page, draft.email);

  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: /متابعة/ }).first()).toBeVisible();
  await expectNoHorizontalScroll(page, "dashboard");

  await page.goto(`/application/${draft.id}/form`);
  await expect(page.getByText("استمارة اشتراك — 2026")).toBeVisible();
  // Below 768 px every beneficiary row is a card, not a table row.
  await expect(page.getByRole("group", { name: "المستفيد رقم 1", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" })).toBeHidden();
  await expect(rowField(page, "اسم المستفيد", 1)).toHaveValue("منى سعيد عبد الله");

  // Second card: SON_MINOR (birth certificate required, from the server's rules).
  await rowField(page, "درجة القرابة", 2).selectOption("SON_MINOR");
  await rowField(page, "اسم المستفيد", 2).fill("عمر كريم سامي");
  await rowField(page, "سنة الميلاد", 2).fill("٢٠١٥"); // Eastern Arabic digits on a phone keyboard
  await page.getByLabel("اسم المقر").fill(draft.doctorName);
  await expect(page.getByText("تم الحفظ")).toBeVisible();
  await expect(rowField(page, "سنة الميلاد", 2)).toHaveValue("2015");

  await page.getByRole("button", { name: /^مستندات المستفيد رقم 2/ }).tap();
  const dialog = page.getByRole("dialog", { name: "مستندات المستفيد: عمر كريم سامي" });
  const slot = dialog.getByRole("group", { name: "شهادة الميلاد", exact: true });
  await slot.getByLabel("شهادة الميلاد", { exact: true }).setInputFiles(fixture("birth-son.png"));
  await expect(slot.getByText("✓ تم الإرفاق: birth-son.png")).toBeVisible();
  const dialogOverflow = await dialog.evaluate((element) => element.scrollWidth - element.clientWidth);
  expect(dialogOverflow, "document dialog fits the phone").toBeLessThanOrEqual(0);
  await dialog.getByRole("button", { name: "حفظ وإغلاق" }).tap();
  await expect(page.getByRole("button", { name: /^مستندات المستفيد رقم 2/ })).toHaveAttribute("data-state", "complete");

  // Server quote: tier 3 member 750 + WIFE 1000 + child 550 + admin fee 175.
  await expect(page.getByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" })).toContainText("2٬475 ج.م");
  await page.evaluate(() => window.scrollTo(0, 0));
  await expectNoHorizontalScroll(page, "form");

  // The sticky action bar stays reachable on the phone.
  const next = page.getByRole("button", { name: "متابعة لرفع الإيصال" });
  await expect(next).toBeInViewport();
  await next.tap();
  await expect(page).toHaveURL(new RegExp(`/application/${draft.id}/payment$`));
  await page.getByLabel("إيصال الدفع", { exact: true }).setInputFiles(fixture("receipt.png"));
  await expect(page.getByRole("group", { name: "الإيصال المرفوع" })).toContainText("receipt.png");
  await expectNoHorizontalScroll(page, "payment");
  await page.getByRole("button", { name: "متابعة للمراجعة" }).tap();

  await expect(page).toHaveURL(new RegExp(`/application/${draft.id}/review$`));
  await expect(page.getByText("الاستمارة مكتملة وجاهزة للتقديم.")).toBeVisible();
  await expectNoHorizontalScroll(page, "review");
  await page.getByRole("checkbox", { name: "أقر بأن جميع البيانات صحيحة وأوافق على نص الإقرار." }).check();
  await page.getByRole("button", { name: "تقديم الطلب" }).tap();

  await expect(page).toHaveURL(new RegExp(`/application/${draft.id}/status$`));
  await expect(page.getByText("تم تقديم طلبك بنجاح")).toBeVisible();
  await expect(page.getByText(/^MED-2026-\d{6}$/)).toBeVisible();
  await expectNoHorizontalScroll(page, "status");
});
