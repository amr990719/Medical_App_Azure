import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { createDraftApplication, pageDevLogin, type BeneficiaryInput } from "./helpers";

/**
 * PROMPT.md §9.8 / §55 "Print view fits A4" under the worst case the form allows: ten
 * beneficiaries (MAX_BENEFICIARIES) with long four- and five-part names and national IDs, printed
 * by the doctor and by the admin. Each PDF must be A4, at most two pages, and nothing may be
 * wider than the page (Chromium clips overflow silently in a PDF).
 *
 * Artefacts: docs/screenshots/session-9/print-a4-{doctor,admin}.pdf
 */
const ARTEFACTS = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots/session-9");
const A4 = { width: 794, height: 1123 }; // 210 × 297 mm at 96 dpi

const TEN: BeneficiaryInput[] = [
  { kinship: "WIFE", full_name: "فاطمة الزهراء عبد الرحمن محمود الشناوي", birth_year: 1988, national_id: "28803120101248" },
  { kinship: "FATHER", full_name: "عبد العزيز مصطفى إبراهيم عبد الغفار", birth_year: 1950, national_id: "25001010101233" },
  { kinship: "MOTHER", full_name: "نعمات عبد الحميد السيد أبو العينين", birth_year: 1955, national_id: "25505050101244" },
  { kinship: "SON_GRADUATE", full_name: "محمد عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2001, national_id: "30103030101259" },
  { kinship: "SON_UNIVERSITY", full_name: "يوسف عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2005, national_id: "30504040101213" },
  { kinship: "SON_MINOR", full_name: "عمر عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2012 },
  { kinship: "SON_MINOR", full_name: "علي عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2015 },
  { kinship: "DAUGHTER", full_name: "مريم عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2008, national_id: "30808080101242" },
  { kinship: "DAUGHTER", full_name: "سلمى عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2014 },
  { kinship: "DAUGHTER", full_name: "نور عبد العزيز مصطفى إبراهيم الشناوي", birth_year: 2018 },
];

/** Page count of a Chromium PDF, from its page-tree root (`/Type /Pages … /Count n`). */
function pdfPageCount(path: string): number {
  const pdf = readFileSync(path, "latin1");
  const leaves = (pdf.match(/\/Type\s*\/Page(?![s\w])/g) ?? []).length;
  const counts = [...pdf.matchAll(/\/Type\s*\/Pages[^>]*?\/Count\s+(\d+)/g)].map((m) => Number(m[1]));
  const root = counts.length ? Math.max(...counts) : leaves;
  expect(root, "page-tree /Count agrees with the page objects").toBe(leaves);
  return root;
}

/** The paper form keeps its inputs in print: the names are input values, row by row. */
async function expectAllRows(page: Page) {
  for (const [index, beneficiary] of TEN.entries()) {
    const name = page.getByLabel(`اسم المستفيد — المستفيد رقم ${index + 1}`, { exact: true });
    await expect(name).toHaveValue(beneficiary.full_name);
  }
}

async function printToPdf(page: Page, name: string): Promise<number> {
  await page.emulateMedia({ media: "print" });
  await page.setViewportSize(A4);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "nothing is wider than an A4 page").toBeLessThanOrEqual(0);
  // An input clips its value without a trace on paper: no printed field may be cut short.
  const clipped = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>("input, textarea"))
      // sr-only summary inputs (1 px, never printed) are not paper fields.
      .filter((field) => field.offsetParent !== null && field.clientWidth > 2 && field.value)
      .filter((field) => field.scrollWidth > field.clientWidth + 1)
      .map((field) => `${field.getAttribute("aria-label") ?? field.name}: ${field.value}`),
  );
  expect(clipped, "printed values cut off by their field").toEqual([]);
  // A submitted application printed for the file carries no client-side validation marks.
  await expect(page.locator('[aria-invalid="true"]')).toHaveCount(0);
  await expect(page.getByText("الرقم القومي يجب أن يكون 14 رقماً صحيحاً")).toHaveCount(0);
  const path = join(ARTEFACTS, name);
  await page.pdf({ path, format: "A4", printBackground: true, preferCSSPageSize: true });
  const pages = pdfPageCount(path);
  console.log(`${name}: ${pages} page(s)`);
  return pages;
}

test.setTimeout(180_000);

test("ten beneficiaries with long names print on at most two A4 pages (doctor and admin)", async ({
  page,
  request,
  browser,
}) => {
  test.skip(test.info().project.name !== "desktop", "print is a desktop/paper concern");
  mkdirSync(ARTEFACTS, { recursive: true });
  const draft = await createDraftApplication(request, {
    doctorName: "عبد العزيز مصطفى إبراهيم عبد الغفار الشناوي",
    beneficiaries: TEN,
  });
  const reference = await draft.submit();
  console.log(`submitted ${reference} with ${TEN.length} beneficiaries`);

  // Doctor's print view.
  await pageDevLogin(page, draft.email);
  await page.goto(`/application/${draft.id}/print`);
  const table = page.getByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" });
  await expect(table).toBeVisible();
  await expectAllRows(page);
  await expect(page.getByText(reference)).toBeVisible();
  expect(await printToPdf(page, "print-a4-doctor.pdf")).toBeLessThanOrEqual(2);

  // Admin's print view of the same application (separate session).
  const admin = await browser.newContext({ baseURL: test.info().project.use.baseURL, locale: "ar-EG" });
  const adminPage = await admin.newPage();
  await pageDevLogin(adminPage, "admin@dev.local");
  await adminPage.goto(`/admin/applications/${draft.id}/print`);
  const adminTable = adminPage.getByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" });
  await expect(adminTable).toBeVisible();
  await expectAllRows(adminPage);
  expect(await printToPdf(adminPage, "print-a4-admin.pdf")).toBeLessThanOrEqual(2);
  await admin.close();
});
