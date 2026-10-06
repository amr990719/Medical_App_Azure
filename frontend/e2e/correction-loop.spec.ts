import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { createSubmittedApplication, openFromAdminList, pageDevLogin, reviewAction } from "./helpers";

/**
 * PROMPT.md §42 "Separate run: request correction → doctor resubmits": the admin asks for a
 * correction with a note, the doctor reads it, fixes the form, goes through receipt and review
 * again and resubmits — the reference number does not change (§16.3).
 */
const ARTEFACTS = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots/session-6");
const NOTE = "يرجى تصحيح اسم الحي في العنوان ثم إعادة التقديم.";

test.setTimeout(120_000);

test("admin requests a correction, the doctor resubmits with the same reference number", async ({
  page,
  request,
  browser,
}) => {
  test.skip(test.info().project.name !== "desktop", "desktop project only");
  const submitted = await createSubmittedApplication(request);
  console.log(`submitted ${submitted.referenceNumber} for ${submitted.email}`);

  // Admin: correction with a doctor-visible note (required).
  await page.setViewportSize({ width: 1280, height: 900 });
  await pageDevLogin(page, "admin@dev.local");
  await openFromAdminList(page, submitted.referenceNumber);
  await page.getByRole("button", { name: "طلب تصحيح", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "تأكيد", exact: true }).click();
  await expect(dialog.getByText("يرجى كتابة ملاحظات المراجعة")).toBeVisible();
  await dialog.getByRole("button", { name: "إلغاء" }).click();
  await reviewAction(page, "طلب تصحيح", NOTE);
  await expect(page.getByText("تم تحديث حالة الطلب إلى: يحتاج تصحيح")).toBeVisible();
  await expect(page.getByRole("region", { name: "ملاحظات المراجعة (تظهر للعضو)" })).toContainText(NOTE);

  // Doctor: sees the note on the dashboard, corrects, resubmits.
  const doctor = await browser.newContext({ baseURL: test.info().project.use.baseURL, locale: "ar-EG" });
  const doctorPage = await doctor.newPage();
  await doctorPage.setViewportSize({ width: 1280, height: 900 });
  await pageDevLogin(doctorPage, submitted.email);
  await doctorPage.goto("/dashboard");
  await expect(doctorPage.getByText(NOTE)).toBeVisible();
  await doctorPage.getByRole("link", { name: "تصحيح وإعادة التقديم" }).first().click();
  await expect(doctorPage).toHaveURL(new RegExp(`/application/${submitted.id}/form$`));

  const neighborhood = doctorPage.getByLabel("الحي :");
  await neighborhood.fill("مصر الجديدة");
  await expect(doctorPage.getByText("تم الحفظ")).toBeVisible();
  await doctorPage.getByRole("button", { name: "متابعة لرفع الإيصال" }).click();
  await expect(doctorPage).toHaveURL(new RegExp(`/application/${submitted.id}/payment$`));
  await doctorPage.getByRole("button", { name: "متابعة للمراجعة" }).click();
  await expect(doctorPage).toHaveURL(new RegExp(`/application/${submitted.id}/review$`));

  const accept = doctorPage.getByRole("checkbox", { name: "أقر بأن جميع البيانات صحيحة وأوافق على نص الإقرار." });
  if (!(await accept.isChecked())) await accept.check();
  const resubmit = doctorPage.getByRole("button", { name: "إعادة تقديم الطلب" });
  await expect(resubmit).toBeEnabled();
  await resubmit.click();

  await expect(doctorPage).toHaveURL(new RegExp(`/application/${submitted.id}/status$`));
  await expect(doctorPage.getByText(/^MED-2026-\d{6}$/)).toHaveText(submitted.referenceNumber);
  await doctorPage.screenshot({ path: join(ARTEFACTS, "doctor-resubmitted-1280.png"), fullPage: true });
  await doctor.close();

  // Admin: the same reference number is back in the queue as مقدم, and the audit says so.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(submitted.referenceNumber);
  const actions = page.getByRole("region", { name: "إجراءات المراجعة" });
  await expect(actions.getByRole("button", { name: "بدء المراجعة" })).toBeVisible();
  await expect(page.getByRole("region", { name: "سجل المراجعة" })).toContainText("إعادة تقديم الطلب");
  await expect(page.getByRole("region", { name: "بيانات العضو" })).toContainText("مصر الجديدة");
});
