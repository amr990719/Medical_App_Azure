import { mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { createSubmittedApplication, openFromAdminList, pageDevLogin, reviewAction } from "./helpers";

/**
 * PROMPT.md §42 "Admin" scenario: the admin finds the submitted application → confirms the
 * payment → starts the review → approves; the doctor then sees مقبول. Real stack: compose
 * Django (development settings, dev auth, Azurite) behind the Vite proxy.
 *
 * Artefacts: docs/screenshots/session-6/*.png
 */
const ARTEFACTS = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots/session-6");

test.setTimeout(120_000);

test("admin finds the submitted application, confirms the payment and approves it", async ({ page, request, browser }) => {
  test.skip(test.info().project.name !== "desktop", "desktop project only (checks 390 px itself)");
  mkdirSync(ARTEFACTS, { recursive: true });
  const submitted = await createSubmittedApplication(request);
  console.log(`submitted ${submitted.referenceNumber} for ${submitted.email}`);

  // Admin dashboard: the §44 tiles.
  await page.setViewportSize({ width: 1280, height: 900 });
  await pageDevLogin(page, "admin@dev.local");
  await page.goto("/admin/dashboard");
  const tiles = page.getByRole("list", { name: "إحصاءات الطلبات" });
  await expect(tiles.getByRole("link", { name: /إيصالات بانتظار التأكيد/ })).toBeVisible();
  await expect(tiles.getByRole("link", { name: /إجمالي الطلبات/ })).toContainText(/\d/);
  await page.screenshot({ path: join(ARTEFACTS, "admin-dashboard-1280.png"), fullPage: true });

  // The "waiting for review" tile opens the filtered list, where the new application appears.
  await tiles.getByRole("link", { name: /بانتظار المراجعة/ }).click();
  await expect(page).toHaveURL(/\/admin\/applications\?status=SUBMITTED$/);
  await expect(page.getByRole("combobox", { name: "الحالة" })).toHaveValue("SUBMITTED");
  await page.getByRole("button", { name: "ترتيب حسب رقم الطلب" }).click();
  await page.getByRole("button", { name: "ترتيب حسب رقم الطلب" }).click(); // descending: newest first
  await expect(page).toHaveURL(/ordering=-reference_number/);
  await expect(page.getByRole("row", { name: new RegExp(submitted.referenceNumber) })).toBeVisible();
  await page.screenshot({ path: join(ARTEFACTS, "admin-applications-1280.png"), fullPage: true });

  // Search by reference number → detail.
  await openFromAdminList(page, submitted.referenceNumber);
  const member = page.getByRole("region", { name: "بيانات العضو" });
  await expect(member).toContainText(submitted.doctorName);
  await expect(member).toContainText(/28•{9}\d{3}/);

  // Document viewer: the receipt through the authorized content endpoint.
  const payment = page.getByRole("region", { name: "إيصال الدفع" });
  await payment.getByRole("button", { name: "عرض الإيصال" }).click();
  const viewer = page.getByRole("dialog", { name: "إيصال الدفع" });
  const image = viewer.getByRole("img", { name: "صورة المستند: إيصال الدفع" });
  await expect(image).toBeVisible();
  expect(await image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await viewer.getByRole("button", { name: "إغلاق" }).click();

  // Approval is not offered before the payment is confirmed.
  const actions = page.getByRole("region", { name: "إجراءات المراجعة" });
  await expect(actions.getByRole("button", { name: "قبول الطلب" })).toHaveCount(0);

  // Confirm payment → start review → approve.
  await reviewAction(page, "تأكيد الدفع");
  await expect(page.getByText("تم تحديث حالة الدفع إلى: مؤكد")).toBeVisible();
  await reviewAction(page, "بدء المراجعة");
  await expect(page.getByText("تم تحديث حالة الطلب إلى: قيد المراجعة")).toBeVisible();
  await reviewAction(page, "قبول الطلب", "مرحباً بك في مشروع العلاج.");
  await expect(page.getByText("تم تحديث حالة الطلب إلى: مقبول")).toBeVisible();
  await expect(actions).toContainText("لا توجد إجراءات متاحة لهذه الحالة.");

  // The audit history records the review.
  const audit = page.getByRole("region", { name: "سجل المراجعة" });
  await expect(audit).toContainText("قيد المراجعة ← مقبول");
  await expect(audit).toContainText("بانتظار التأكيد ← مؤكد");
  await page.screenshot({ path: join(ARTEFACTS, "admin-detail-approved-1280.png"), fullPage: true });

  // Phones: the list and the detail fit 390 px without horizontal scrolling.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/admin/applications", `/admin/applications/${submitted.id}`]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
  await page.screenshot({ path: join(ARTEFACTS, "admin-detail-390.png"), fullPage: true });

  // The doctor sees the decision.
  const doctor = await browser.newContext({ baseURL: test.info().project.use.baseURL, locale: "ar-EG" });
  const doctorPage = await doctor.newPage();
  await pageDevLogin(doctorPage, submitted.email);
  await doctorPage.goto(`/application/${submitted.id}/status`);
  await expect(doctorPage.getByText("تم قبول الطلب")).toBeVisible();
  await expect(doctorPage.getByText(submitted.referenceNumber)).toBeVisible();
  await expect(doctorPage.getByText("مرحباً بك في مشروع العلاج.")).toBeVisible();
  await doctor.close();
});
