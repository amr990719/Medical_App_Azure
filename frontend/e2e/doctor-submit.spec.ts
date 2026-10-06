import { readFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * Session 5 doctor journey against the real backend (development settings: DEV_AUTH_ENABLED,
 * mock OCR, Azurite blobs) through the Vite proxy — PROMPT.md §42 "Doctor" scenario with the
 * worked example 2 data (2014 / WORKING / 1985, WIFE 1988, SON_MINOR 2015, DAUGHTER 2018 → 3025).
 *
 * Artefacts: docs/screenshots/session-5/{form-1280.png, form-390.png, status-1280.png, print-a4.pdf}.
 */
const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name: string) => join(here, "fixtures", name);
const ARTEFACTS = resolve(here, "../../docs/screenshots/session-5");

test.setTimeout(180_000);

/** A fresh doctor for every run (dev-only `create` flag), so the flow always starts from no application. */
async function signInAsFreshDoctor(page: Page) {
  await page.goto("/");
  await page.request.get("/api/v1/auth/me/"); // sets the csrftoken cookie
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === "csrftoken")?.value ?? "";
  const email = `e2e-${Date.now()}@dev.local`;
  const response = await page.request.post("/api/v1/auth/dev/login/", {
    data: { email, create: true },
    headers: { "X-CSRFToken": csrf },
  });
  expect(response.ok()).toBeTruthy();
}

/** A valid, unused national ID for a man born 1985-06-15 (position 13 odd), unique per run. */
function uniqueMaleNationalId(): string {
  const serial = String(Math.floor(Math.random() * 1000)).padStart(3, "0");
  const odd = [1, 3, 5, 7, 9][Math.floor(Math.random() * 5)];
  return `2850615` + `01` + serial + String(odd) + String(Math.floor(Math.random() * 10));
}

async function uploadInSlot(scope: Page | Locator, label: string, file: string) {
  const slot = scope.getByRole("group", { name: label, exact: true });
  await slot.getByLabel(label, { exact: true }).setInputFiles(fixture(file));
  await expect(slot.getByText(`✓ تم الإرفاق: ${file}`)).toBeVisible();
  return slot;
}

async function scan(slot: Locator) {
  await slot.getByRole("button", { name: "مسح تلقائي" }).click();
  await expect(slot.getByText("✓ تم استخراج البيانات — راجع الحقول أدناه وعدّل إن لزم")).toBeVisible();
}

const rowField = (page: Page, field: string, n: number) => page.getByLabel(`${field} — المستفيد رقم ${n}`, { exact: true });

async function waitSaved(page: Page) {
  await expect(page.getByText("تم الحفظ")).toBeVisible();
}

test("doctor fills the paper form with OCR, adds family, pays, submits and gets a reference number", async ({
  page,
}) => {
  // One run is enough: the flow resizes to 390 px itself for the phone layout check.
  test.skip(test.info().project.name !== "desktop", "desktop project only");
  mkdirSync(ARTEFACTS, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await signInAsFreshDoctor(page);

  // /application/new creates the draft and opens the first step.
  await page.goto("/application/new");
  await expect(page).toHaveURL(/\/application\/[0-9a-f-]{36}\/form$/);
  const applicationUrl = page.url().replace(/\/form$/, "");
  await expect(page.getByText("استمارة اشتراك — 2026")).toBeVisible();

  // 1. ID front → mock OCR fills the empty member fields.
  const front = await uploadInSlot(page, "صورة البطاقة (وجه)", "id-front.png");
  await scan(front);
  await expect(page.getByLabel("أسم العضو :")).toHaveValue("أحمد محمد علي حسن");
  await expect(page.getByLabel("سنة الميلاد :")).toHaveValue("1985");
  await expect(page.getByLabel("محافظة السكن :")).toHaveValue("القاهرة");
  await expect(page.getByLabel("الحي :")).toHaveValue("مدينة نصر");
  await expect(page.getByRole("radio", { name: "ذكر" })).toBeChecked();
  await expect(page.getByRole("textbox", { name: "الرقم القومي :", exact: true })).toHaveValue("28506150101234");

  // The mock always returns the same ID; give this run's doctor a unique one (UNIQUE constraint).
  const firstBox = page.getByRole("group", { name: "الرقم القومي :", exact: true }).getByRole("textbox").first();
  await firstBox.click();
  await page.keyboard.insertText(uniqueMaleNationalId());

  // 2. ID back and syndicate card.
  await scan(await uploadInSlot(page, "صورة البطاقة (ظهر)", "id-back.png"));
  await expect(page.getByRole("radio", { name: "مسلم" })).toBeChecked();
  await scan(await uploadInSlot(page, "كارنيه النقابة", "syndicate-card.png"));
  await expect(page.getByRole("radio", { name: "بشري" })).toBeChecked();
  await expect(page.getByLabel("سنة قيد النقابة :")).toHaveValue("2014");
  await expect(page.getByLabel("رقم قيد النقابة :")).toHaveValue("12345");

  // 3. What OCR cannot read.
  await page.getByText("يعمل", { exact: true }).click();
  await page.getByLabel("المحمول :").fill("01012345678");
  await page.getByLabel("اسم المقر").fill("أحمد محمد علي حسن");
  await waitSaved(page);

  // 4. Beneficiaries: WIFE with three documents.
  await rowField(page, "درجة القرابة", 1).selectOption("WIFE");
  await rowField(page, "اسم المستفيد", 1).fill("منى سعيد عبد الله");
  await rowField(page, "سنة الميلاد", 1).fill("1988");
  await waitSaved(page);
  await page.getByRole("button", { name: /^مستندات المستفيد رقم 1/ }).click();
  let dialog = page.getByRole("dialog", { name: "مستندات المستفيد: منى سعيد عبد الله" });
  await uploadInSlot(dialog, "بطاقة الرقم القومي", "spouse-id.png");
  await uploadInSlot(dialog, "شهادة الزواج", "marriage.png");
  await uploadInSlot(dialog, "برينت تأميني", "insurance.png");
  await dialog.getByRole("button", { name: "حفظ وإغلاق" }).click();
  await expect(page.getByRole("button", { name: /^مستندات المستفيد رقم 1/ })).toHaveAttribute("data-state", "complete");

  // SON_MINOR: the birth certificate's OCR fills the empty name and birth year.
  await rowField(page, "درجة القرابة", 2).selectOption("SON_MINOR");
  await page.getByRole("button", { name: /^مستندات المستفيد رقم 2/ }).click();
  dialog = page.getByRole("dialog", { name: /^مستندات المستفيد: / });
  await scan(await uploadInSlot(dialog, "شهادة الميلاد", "birth-son.png"));
  await dialog.getByRole("button", { name: "حفظ وإغلاق" }).click();
  await expect(rowField(page, "اسم المستفيد", 2)).toHaveValue("عمر أحمد محمد");
  await expect(rowField(page, "سنة الميلاد", 2)).toHaveValue("2015");
  await waitSaved(page);
  await expect(page.getByRole("button", { name: /^مستندات المستفيد رقم 2/ })).toHaveAttribute("data-state", "complete");

  // DAUGHTER (worked example 2).
  await rowField(page, "درجة القرابة", 3).selectOption("DAUGHTER");
  await rowField(page, "اسم المستفيد", 3).fill("مريم أحمد محمد");
  await rowField(page, "سنة الميلاد", 3).fill("2018");
  await waitSaved(page);
  await page.getByRole("button", { name: /^مستندات المستفيد رقم 3/ }).click();
  dialog = page.getByRole("dialog", { name: "مستندات المستفيد: مريم أحمد محمد" });
  await uploadInSlot(dialog, "شهادة الميلاد", "birth-daughter.png");
  await dialog.getByRole("button", { name: "حفظ وإغلاق" }).click();

  // 5. The server's quote: tier 3, 750 + 1000 + 550 + 550 + 175.
  const fees = page.getByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" });
  await expect(fees).toContainText("الدرجة 3");
  await expect(fees).toContainText("3٬025 ج.م");
  await expect(page.getByRole("group", { name: "العضو الأصلي" })).not.toContainText("غير مرفق");

  // Screenshots at 1280 px and 390 px (no horizontal scrolling on the phone layout).
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ARTEFACTS, "form-1280.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("group", { name: "المستفيد رقم 1", exact: true })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: join(ARTEFACTS, "form-390.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });

  // 6. Continue → server validation of steps 1–3 → receipt.
  await page.getByRole("button", { name: "متابعة لرفع الإيصال" }).click();
  await expect(page).toHaveURL(`${applicationUrl}/payment`);
  await expect(page.getByRole("region", { name: "ملخص الرسوم" })).toContainText("3٬025 ج.م");
  await page.getByLabel("إيصال الدفع", { exact: true }).setInputFiles(fixture("receipt.png"));
  await expect(page.getByRole("group", { name: "الإيصال المرفوع" })).toContainText("receipt.png");
  await expect(page.getByText("حالة الدفع: بانتظار التأكيد")).toBeVisible();
  await page.getByRole("button", { name: "متابعة للمراجعة" }).click();

  // 7. Review → acceptance → submit.
  await expect(page).toHaveURL(`${applicationUrl}/review`);
  await expect(page.getByText("الاستمارة مكتملة وجاهزة للتقديم.")).toBeVisible();
  await page.getByRole("checkbox", { name: "أقر بأن جميع البيانات صحيحة وأوافق على نص الإقرار." }).check();
  const submit = page.getByRole("button", { name: "تقديم الطلب" });
  await expect(submit).toBeEnabled();
  await submit.click();

  // 8. Reference number.
  await expect(page).toHaveURL(`${applicationUrl}/status`);
  await expect(page.getByText("تم تقديم طلبك بنجاح")).toBeVisible();
  const reference = page.getByText(/^MED-2026-\d{6}$/);
  await expect(reference).toBeVisible();
  console.log(`submitted ${await reference.textContent()}`);
  await page.screenshot({ path: join(ARTEFACTS, "status-1280.png"), fullPage: true });

  // 9. A4 print view → PDF within two pages.
  await page.goto(`${applicationUrl}/print`);
  await expect(page.getByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" })).toBeVisible();
  await expect(page.getByText(/^MED-2026-\d{6}$/)).toBeVisible();
  await page.emulateMedia({ media: "print" });
  await page.setViewportSize({ width: 794, height: 1123 }); // A4 at 96 dpi
  await page.screenshot({ path: join(ARTEFACTS, "print-a4-preview.png"), fullPage: true });
  const pdfPath = join(ARTEFACTS, "print-a4.pdf");
  await page.pdf({ path: pdfPath, format: "A4", printBackground: true, preferCSSPageSize: true });
  const pages = (readFileSync(pdfPath, "latin1").match(/\/Type\s*\/Page(?!s)/g) ?? []).length;
  console.log(`print-a4.pdf pages: ${pages}`);
  expect(pages).toBeGreaterThanOrEqual(1);
  expect(pages).toBeLessThanOrEqual(2);
});
