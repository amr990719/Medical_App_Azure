/**
 * The member's own birth certificate is required while an active MOTHER is listed — a rule the
 * server evaluates into `member_required_documents` (D154). These tests drive the real autosave
 * path against a stateful fake backend: the requirement must follow beneficiary saves without a
 * page reload or an unrelated upload, and unsaved edits must survive the refetch.
 */
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useValidation } from "@/features/applications/useValidation";
import { BeneficiaryTable } from "@/features/beneficiaries/BeneficiaryTable";
import { DocumentsChecklist } from "@/features/documents/DocumentsChecklist";
import { useFeeQuote } from "@/features/fees/useFeeQuote";
import {
  API,
  APP_ID,
  apiApplication,
  apiBeneficiary,
  apiDocument,
  apiProfile,
  apiReferenceData,
  cleanValidation,
  feeQuote,
  MEMBER_BIRTH_CERTIFICATE_REQUIREMENT,
  MOTHER_REQUIREMENTS,
  SPOUSE_REQUIREMENTS,
  type ApiBeneficiary,
  type ApiDocument,
} from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { FAST_DRAFT } from "@/test/renderForm";
import { server } from "@/test/server";
import { ApplicationFormProvider } from "./ApplicationFormProvider";

const CERTIFICATE = "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم";
const MEMBER_SECTION = "مستند خاص بالعضو الأصلي";
const BASE_MEMBER_SLOTS = apiReferenceData.document_rules.member as unknown as Record<string, unknown>[];

/** The server stores "" for a row without kinship (`blank=True`); the generated type omits it. */
type StoredRow = Omit<ApiBeneficiary, "kinship"> & { kinship: ApiBeneficiary["kinship"] | "" };

type Gate = { promise: Promise<void>; open: () => void };
const gate = (): Gate => {
  let open = () => {};
  const promise = new Promise<void>((resolve) => (open = resolve));
  return { promise, open };
};

/**
 * Minimal stand-in for the backend. Only this test double knows the MOTHER rule; the SPA reads
 * whatever `member_required_documents` the server returns.
 */
function fakeBackend({
  beneficiaries = [] as ApiBeneficiary[],
  documents = [] as ApiDocument[],
} = {}) {
  const db: { beneficiaries: StoredRow[]; documents: ApiDocument[] } = {
    beneficiaries: [...beneficiaries],
    documents: [...documents],
  };
  const calls = { application: 0, fees: 0, validation: 0, documentDeletes: 0 };
  const gates: { application?: Gate; beneficiaryWrite?: Gate } = {};

  const isActive = (b: StoredRow) => Boolean(b.kinship) && b.full_name.trim() !== "";
  const memberSlots = () => {
    const activeMother = db.beneficiaries.some((b) => b.kinship === "MOTHER" && isActive(b));
    const uploaded = db.documents.some((d) => d.document_type === "MEMBER_BIRTH_CERTIFICATE" && !d.beneficiary_id);
    if (activeMother) return [...BASE_MEMBER_SLOTS, MEMBER_BIRTH_CERTIFICATE_REQUIREMENT];
    if (uploaded) return [...BASE_MEMBER_SLOTS, { ...MEMBER_BIRTH_CERTIFICATE_REQUIREMENT, required: false }];
    return BASE_MEMBER_SLOTS;
  };
  const stored = (b: StoredRow): ApiBeneficiary => ({
    ...(b as ApiBeneficiary),
    is_active: isActive(b),
    required_documents: b.kinship === "MOTHER" ? MOTHER_REQUIREMENTS : b.kinship ? SPOUSE_REQUIREMENTS : [],
    documents: db.documents.filter((d) => d.beneficiary_id === b.id),
  });
  const snapshot = () =>
    apiApplication({
      beneficiaries: db.beneficiaries.map(stored),
      documents: db.documents,
      member_required_documents: memberSlots(),
    });

  const base = `${API}/applications/${APP_ID}`;
  server.use(
    http.get(`${API}/profile/`, () => HttpResponse.json(apiProfile({ gender: "MALE" }))),
    http.get(`${base}/`, async () => {
      calls.application += 1;
      const body = snapshot(); // what the server knew when the request arrived
      await gates.application?.promise;
      return HttpResponse.json(body);
    }),
    http.get(`${base}/fees/`, () => {
      calls.fees += 1;
      return HttpResponse.json(feeQuote);
    }),
    http.get(`${base}/validation/`, () => {
      calls.validation += 1;
      return HttpResponse.json(cleanValidation);
    }),
    http.post(`${base}/beneficiaries/`, async ({ request }) => {
      await gates.beneficiaryWrite?.promise;
      const body = (await request.json()) as Partial<ApiBeneficiary>;
      const row: StoredRow = { ...apiBeneficiary({ full_name: "", birth_year: null }), kinship: "", ...body, id: `b-${body.row_number}` };
      db.beneficiaries.push(row);
      return HttpResponse.json(stored(row), { status: 201 });
    }),
    http.patch(`${base}/beneficiaries/:id/`, async ({ request, params }) => {
      await gates.beneficiaryWrite?.promise;
      const body = (await request.json()) as Partial<ApiBeneficiary>;
      const index = db.beneficiaries.findIndex((b) => b.id === params.id);
      const before = db.beneficiaries[index]!;
      if (body.kinship !== undefined && body.kinship !== before.kinship) {
        db.documents = db.documents.filter((d) => d.beneficiary_id !== before.id); // §9.5
      }
      db.beneficiaries[index] = { ...before, ...body };
      return HttpResponse.json(stored(db.beneficiaries[index]!));
    }),
    http.delete(`${base}/beneficiaries/:id/`, ({ params }) => {
      db.beneficiaries = db.beneficiaries.filter((b) => b.id !== params.id);
      db.documents = db.documents.filter((d) => d.beneficiary_id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
    http.delete(`${API}/documents/:id/`, () => {
      calls.documentDeletes += 1;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { db, calls, gates };
}

/** The form page also shows the fee quote and the validation: keep both queries observed. */
function DerivedQueries() {
  useFeeQuote(APP_ID);
  useValidation(APP_ID);
  return null;
}

async function renderForm() {
  const view = renderWithProviders(
    <ApplicationFormProvider applicationId={APP_ID} options={FAST_DRAFT}>
      <DerivedQueries />
      <BeneficiaryTable layout="table" />
      <DocumentsChecklist />
    </ApplicationFormProvider>,
  );
  await screen.findByRole("group", { name: "العضو الأصلي" });
  return view;
}

const memberGroup = () => screen.getByRole("group", { name: "العضو الأصلي" });
/** The certificate's state in the member checklist: missing / optional / attached, or null. */
const certificateState = () => {
  const label = within(memberGroup()).queryByText(CERTIFICATE);
  return label?.closest("li")?.querySelector("[data-state]")?.getAttribute("data-state") ?? null;
};
const kinship = (row: number) => screen.getByRole("combobox", { name: `درجة القرابة — المستفيد رقم ${row}` });
const nameInput = (row: number) => screen.getByRole("textbox", { name: `اسم المستفيد — المستفيد رقم ${row}` });

const mother = (overrides: Partial<ApiBeneficiary> = {}) =>
  apiBeneficiary({ id: "b-1", row_number: 1, kinship: "MOTHER", full_name: "فاطمة علي أحمد", birth_year: 1960, ...overrides });
const memberCertificate = apiDocument({ id: "d-mbc", document_type: "MEMBER_BIRTH_CERTIFICATE", beneficiary_id: null });

// Real typing through the real autosave path: slower than a unit test under a parallel run.
describe("member requirements follow beneficiary saves (MOTHER → member birth certificate)", { timeout: 15_000 }, () => {
  it("shows the certificate as soon as an active mother is saved: checklist and her dialog", async () => {
    const backend = fakeBackend();
    const { user } = await renderForm();
    expect(certificateState()).toBeNull();
    await waitFor(() => expect(backend.calls.fees).toBe(1));
    const before = { ...backend.calls };

    await user.selectOptions(kinship(1), "MOTHER");
    await user.type(nameInput(1), "فاطمة علي أحمد");

    await waitFor(() => expect(certificateState()).toBe("missing"));
    expect(backend.db.beneficiaries).toHaveLength(1);
    // Fees and validation were refreshed together with the application, from the same saves.
    expect(backend.calls.application).toBeGreaterThan(before.application);
    expect(backend.calls.fees).toBeGreaterThan(before.fees);
    expect(backend.calls.validation).toBeGreaterThan(before.validation);

    await user.click(screen.getByRole("button", { name: /مستندات المستفيد رقم 1/ }));
    const dialog = screen.getByRole("dialog", { name: "مستندات المستفيد: فاطمة علي أحمد" });
    expect(within(within(dialog).getByRole("region", { name: MEMBER_SECTION })).getByText(CERTIFICATE)).toBeInTheDocument();
  });

  it("drops the requirement when the mother's kinship changes", async () => {
    fakeBackend({ beneficiaries: [mother()] });
    const { user } = await renderForm();
    expect(certificateState()).toBe("missing");

    await user.selectOptions(kinship(1), "FATHER");

    await waitFor(() => expect(certificateState()).toBeNull());
  });

  it("drops the requirement when the mother's name is cleared (inactive row)", async () => {
    fakeBackend({ beneficiaries: [mother()] });
    const { user } = await renderForm();
    expect(certificateState()).toBe("missing");

    await user.clear(nameInput(1));

    await waitFor(() => expect(certificateState()).toBeNull());
    expect(screen.queryByRole("dialog")).toBeNull(); // kinship kept: no deletion prompt
  });

  it("drops the requirement when the mother is deleted and no certificate was uploaded", async () => {
    const backend = fakeBackend({ beneficiaries: [mother()] });
    const { user } = await renderForm();
    expect(certificateState()).toBe("missing");

    await user.click(screen.getByRole("button", { name: "مسح بيانات المستفيد رقم 1" }));
    await user.click(within(screen.getByRole("dialog", { name: "حذف المستفيد؟" })).getByRole("button", { name: "حذف المستفيد" }));

    await waitFor(() => expect(certificateState()).toBeNull());
    expect(backend.db.beneficiaries).toHaveLength(0);
  });

  it("keeps an uploaded certificate, now optional, when the mother is deleted", async () => {
    const backend = fakeBackend({ beneficiaries: [mother()], documents: [memberCertificate] });
    const { user, queryClient } = await renderForm();
    expect(certificateState()).toBe("attached");

    await user.click(screen.getByRole("button", { name: "مسح بيانات المستفيد رقم 1" }));
    await user.click(within(screen.getByRole("dialog", { name: "حذف المستفيد؟" })).getByRole("button", { name: "حذف المستفيد" }));

    // The server now lists the slot as optional; the upload stays visible and is never deleted.
    await waitFor(() => {
      const app = queryClient.getQueryData<{ memberRequiredDocuments: { type: string; required: boolean }[] }>([
        "applications",
        "detail",
        APP_ID,
      ]);
      expect(app?.memberRequiredDocuments.find((slot) => slot.type === "MEMBER_BIRTH_CERTIFICATE")?.required).toBe(false);
    });
    expect(certificateState()).toBe("attached");
    expect(backend.calls.documentDeletes).toBe(0);
    expect(backend.db.documents).toEqual([memberCertificate]);
  });

  it("keeps the requirement while another active mother remains", async () => {
    fakeBackend({ beneficiaries: [mother(), mother({ id: "b-2", row_number: 2, full_name: "سعاد محمود" })] });
    const { user } = await renderForm();
    expect(certificateState()).toBe("missing");

    await user.click(screen.getByRole("button", { name: "مسح بيانات المستفيد رقم 1" }));
    await user.click(within(screen.getByRole("dialog", { name: "حذف المستفيد؟" })).getByRole("button", { name: "حذف المستفيد" }));

    await waitFor(() => expect(nameInput(1)).toHaveValue(""));
    await waitFor(() => expect(screen.queryByRole("group", { name: "فاطمة علي أحمد — أم" })).toBeNull());
    expect(certificateState()).toBe("missing");
  });

  it("keeps unsaved and in-flight edits while the application is refetched, without a refetch loop", async () => {
    const backend = fakeBackend();
    const { user } = await renderForm();
    const initialLoads = backend.calls.application;

    // Save an active mother, but hold the refetch that follows it.
    backend.gates.application = gate();
    await user.selectOptions(kinship(1), "MOTHER");
    await user.type(nameInput(1), "فاطمة علي أحمد");
    await waitFor(() => expect(backend.db.beneficiaries[0]?.full_name).toBe("فاطمة علي أحمد"));
    await waitFor(() => expect(backend.calls.application).toBeGreaterThan(initialLoads));

    // Meanwhile the doctor keeps typing: row 2 is held in flight, row 3 is still local.
    backend.gates.beneficiaryWrite = gate();
    await user.selectOptions(kinship(2), "WIFE");
    await user.type(nameInput(2), "منى سعيد");
    await user.type(nameInput(3), "عمر");

    backend.gates.application.open();
    await waitFor(() => expect(certificateState()).toBe("missing"));
    expect(nameInput(1)).toHaveValue("فاطمة علي أحمد");
    expect(kinship(2)).toHaveValue("WIFE");
    expect(nameInput(2)).toHaveValue("منى سعيد");
    expect(nameInput(3)).toHaveValue("عمر");

    backend.gates.beneficiaryWrite.open();
    await waitFor(() => expect(backend.db.beneficiaries.map((b) => b.full_name)).toEqual(["فاطمة علي أحمد", "منى سعيد", "عمر"]));
    await waitFor(() => expect(screen.getByRole("group", { name: "منى سعيد — زوجة" })).toBeInTheDocument());
    expect(nameInput(2)).toHaveValue("منى سعيد");
    expect(certificateState()).toBe("missing");

    // Settled: no further requests (a refetch must never trigger another save or refetch).
    const settled = { ...backend.calls };
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(backend.calls).toEqual(settled);
  });
});
