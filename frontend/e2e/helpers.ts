import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type APIRequestContext, type APIResponse, type Page } from "@playwright/test";

/**
 * Shared end-to-end helpers. Everything goes through the Vite proxy to the development backend
 * (DEV_AUTH_ENABLED, mock OCR, Azurite), exactly like the SPA: CSRF token from the cookie.
 */
const here = dirname(fileURLToPath(import.meta.url));
export const fixture = (name: string) => join(here, "fixtures", name);

async function csrfToken(request: APIRequestContext): Promise<string> {
  await request.get("/api/v1/auth/me/"); // 401 when signed out, but always sets csrftoken
  const state = await request.storageState();
  return state.cookies.find((cookie) => cookie.name === "csrftoken")?.value ?? "";
}

/** Dev sign-in of an API context (`create` makes a fresh DOCTOR for an unknown e-mail, D68). */
export async function apiDevLogin(request: APIRequestContext, email: string, create = false) {
  const response = await request.post("/api/v1/auth/dev/login/", {
    data: { email, create },
    headers: { "X-CSRFToken": await csrfToken(request) },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

/**
 * Dev sign-in of a browser page (shares the page's cookie jar). The SPA's own GET /auth/me/
 * also sets `csrftoken`; wait for it first, otherwise its response can replace the cookie after
 * the token was read and the login is refused with a CSRF 403.
 */
export async function pageDevLogin(page: Page, email: string, create = false) {
  await Promise.all([
    page.waitForResponse((response) => response.url().endsWith("/api/v1/auth/me/")),
    page.goto("/"),
  ]);
  await apiDevLogin(page.request, email, create);
}

/** Parallel workers can share a millisecond: add randomness so e-mails never collide. */
export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@dev.local`;
}

/** A valid, unused national ID for a man born 1985-06-15 (position 13 odd), unique per run. */
export function uniqueMaleNationalId(): string {
  const serial = String(Math.floor(Math.random() * 1000)).padStart(3, "0");
  const odd = [1, 3, 5, 7, 9][Math.floor(Math.random() * 5)];
  return `2850615` + `01` + serial + String(odd) + String(Math.floor(Math.random() * 10));
}

export type SubmittedApplication = { id: string; referenceNumber: string; email: string; doctorName: string };

/**
 * A fresh doctor with a SUBMITTED application (member + WIFE, every required document, receipt,
 * declaration), created through the doctor API in a separate cookie jar. The doctor UI journey
 * itself is covered by doctor-submit.spec.ts; the admin specs start from this point.
 */
export async function createSubmittedApplication(request: APIRequestContext): Promise<SubmittedApplication> {
  const draft = await createDraftApplication(request, {
    beneficiaries: [{ kinship: "WIFE", full_name: "منى سعيد عبد الله", birth_year: 1988 }],
  });
  return { ...draft, referenceNumber: await draft.submit() };
}

export type BeneficiaryInput = { kinship: string; full_name: string; birth_year: number; national_id?: string };

export type DraftOptions = {
  beneficiaries?: BeneficiaryInput[];
  doctorName?: string;
  /** Upload the payment receipt and accept the declaration (everything but the submit itself). */
  complete?: boolean;
  /** Upload every required beneficiary document (from the server's own rules). */
  beneficiaryDocuments?: boolean;
};

export type DraftApplication = {
  id: string;
  email: string;
  doctorName: string;
  /** Submit the (complete) draft and return its reference number. */
  submit: () => Promise<string>;
};

/** One fixture image per document type; the dev backend's mock OCR does not read them. */
const FIXTURE_FOR: Record<string, string> = {
  NATIONAL_ID_FRONT: "id-front.png",
  NATIONAL_ID_BACK: "id-back.png",
  SYNDICATE_ID: "syndicate-card.png",
  BENEFICIARY_NATIONAL_ID: "spouse-id.png",
  MARRIAGE_CERTIFICATE: "marriage.png",
  INSURANCE_PRINT: "insurance.png",
  BIRTH_CERTIFICATE: "birth-son.png",
  UNIVERSITY_ID: "syndicate-card.png",
  PAYMENT_RECEIPT: "receipt.png",
};

/**
 * A fresh doctor (profile, WORKING, member documents) with a DRAFT application, created through
 * the doctor API in its own cookie jar. Beneficiary documents follow each row's
 * `required_documents` as answered by the server — THE rules table (§15), never a copy here.
 */
export async function createDraftApplication(
  request: APIRequestContext,
  { beneficiaries = [], doctorName = "كريم سامي عبد الحميد", complete = true, beneficiaryDocuments = true }: DraftOptions = {},
): Promise<DraftApplication> {
  const email = uniqueEmail("e2e-admin");
  await apiDevLogin(request, email, true);
  const headers = { "X-CSRFToken": await csrfToken(request) };
  const ok = async <T = unknown>(response: APIResponse): Promise<T> => {
    expect(response.ok(), `${response.url()} → ${response.status()} ${await response.text()}`).toBeTruthy();
    return (await response.json()) as T;
  };

  await ok(
    await request.patch("/api/v1/profile/", {
      headers,
      data: {
        full_name: doctorName,
        national_id: uniqueMaleNationalId(),
        religion: "MUSLIM",
        phone_number: "01012345678",
        syndicate_type: "HUMAN_MEDICINE",
        sub_syndicate: "القاهرة",
        syndicate_registration_number: String(Date.now()).slice(-6),
        syndicate_registration_year: 2014,
        governorate: "القاهرة",
        neighborhood: "مدينة نصر",
        address: "شارع عباس العقاد",
      },
    }),
  );
  const app = await ok<{ id: string }>(await request.post("/api/v1/applications/", { headers }));
  const base = `/api/v1/applications/${app.id}/`;
  await ok(await request.patch(base, { headers, data: { work_status: "WORKING" } }));

  const upload = async (documentType: string, beneficiaryId?: string) => {
    const file = FIXTURE_FOR[documentType];
    const multipart: Record<string, string | { name: string; mimeType: string; buffer: Buffer }> = {
      document_type: documentType,
      file: { name: file, mimeType: "image/png", buffer: readFileSync(fixture(file)) },
    };
    if (beneficiaryId) multipart.beneficiary_id = beneficiaryId;
    await ok(await request.post(`${base}documents/`, { headers, multipart }));
  };
  await upload("NATIONAL_ID_FRONT");
  await upload("NATIONAL_ID_BACK");
  await upload("SYNDICATE_ID");

  for (const beneficiary of beneficiaries) {
    const row = await ok<{ id: string; required_documents: { type: string; required: boolean }[] }>(
      await request.post(`${base}beneficiaries/`, { headers, data: beneficiary }),
    );
    if (!beneficiaryDocuments) continue;
    for (const slot of row.required_documents.filter((document) => document.required)) {
      await upload(slot.type, row.id);
    }
  }

  if (complete) {
    await upload("PAYMENT_RECEIPT");
    await ok(await request.patch(base, { headers, data: { declaration_name: doctorName, declaration_accepted: true } }));
  }
  const submit = async () => {
    const submitted = await ok<{ reference_number: string }>(await request.post(`${base}submit/`, { headers }));
    expect(submitted.reference_number).toMatch(/^MED-2026-\d{6}$/);
    return submitted.reference_number;
  };
  return { id: app.id, email, doctorName, submit };
}

/** Admin opens the application from the list by searching its reference number. */
export async function openFromAdminList(page: Page, referenceNumber: string) {
  await page.goto("/admin/applications");
  await page.getByRole("searchbox", { name: "بحث" }).fill(referenceNumber);
  await page.getByRole("button", { name: "بحث", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`search=${referenceNumber}`));
  await page.getByRole("link", { name: referenceNumber }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(referenceNumber);
}

/** Click a review action, optionally type notes, confirm, and wait for the server's answer. */
export async function reviewAction(page: Page, action: string, notes = "") {
  await page.getByRole("button", { name: action, exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  if (notes) await dialog.getByRole("textbox").fill(notes);
  await dialog.getByRole("button", { name: "تأكيد", exact: true }).click();
  await expect(dialog).toBeHidden();
}
