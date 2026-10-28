/**
 * Server-evaluated document slots must follow the saves that change them, without a page reload
 * or an unrelated upload, and unsaved edits must survive the refetch:
 * - the member's own birth certificate while an active MOTHER is listed (`member_required_documents`, D154);
 * - each child's slots, which depend on the member's gender as stored by the server (a female
 *   member's children always need a birth certificate) — typed, or derived from the national ID.
 * The tests drive the real autosave path against a stateful fake backend.
 */
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { useValidation } from "@/features/applications/useValidation";
import { BeneficiaryTable } from "@/features/beneficiaries/BeneficiaryTable";
import { DocumentsChecklist } from "@/features/documents/DocumentsChecklist";
import { useFeeQuote } from "@/features/fees/useFeeQuote";
import { MemberSection } from "./MemberSection";
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
  type ApiProfile,
} from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { FAST_DRAFT } from "@/test/renderForm";
import { server } from "@/test/server";
import { ApplicationFormProvider } from "./ApplicationFormProvider";

const CERTIFICATE = "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم";
const BIRTH_CERTIFICATE = "شهادة ميلاد المستفيد";
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

const FISCAL_YEAR = 2026;
const CHILD_ID_AGE = 16;
const CHILD_KINSHIPS = new Set(["SON_MINOR", "SON_UNIVERSITY", "SON_GRADUATE"]);
const slot = (type: string, label: string, required: boolean) => ({
  type, label, required, ocr_capable: false, stage: "form", images_only: false, hints: [] as string[],
});  // fmt: skip

/**
 * A child's slots as the server lists them (`document_rules.py`): both ID sides required from
 * CHILD_ID_AGE (optional below), the birth certificate always offered and required only when the
 * MEMBER is female (whatever the child's age), plus the kinship's own document.
 */
function childSlots(kinship: string, birthYear: number | null | undefined, memberGender: string | undefined) {
  const age = birthYear === null || birthYear === undefined ? null : FISCAL_YEAR - birthYear;
  const younger = age === null || age < CHILD_ID_AGE;
  const slots = [
    slot("BENEFICIARY_NATIONAL_ID", "بطاقة الرقم القومي للمستفيد (وجه)", !younger),
    slot("BENEFICIARY_NATIONAL_ID_BACK", "بطاقة الرقم القومي للمستفيد (ظهر)", !younger),
  ];
  slots.push(slot("BIRTH_CERTIFICATE", BIRTH_CERTIFICATE, memberGender === "FEMALE"));
  if (kinship === "SON_UNIVERSITY") slots.push(slot("UNIVERSITY_ID", "كارنيه الجامعة", true));
  if (kinship === "SON_GRADUATE") slots.push(slot("INSURANCE_PRINT", "برينت تأميني", true));
  return slots;
}

/** Gender from the 13th digit of an Egyptian national ID: odd = male, even = female. */
const genderOf = (nationalId: string) => (Number(nationalId[12]) % 2 === 1 ? "MALE" : "FEMALE");

/**
 * Minimal stand-in for the backend. Only this test double knows the rules; the SPA reads
 * whatever slots the server returns.
 */
function fakeBackend({
  beneficiaries = [] as ApiBeneficiary[],
  documents = [] as ApiDocument[],
  profile = apiProfile({ gender: "MALE" }) as ApiProfile,
} = {}) {
  const db: { beneficiaries: StoredRow[]; documents: ApiDocument[]; profile: ApiProfile } = {
    beneficiaries: [...beneficiaries],
    documents: [...documents],
    profile,
  };
  const calls = { application: 0, fees: 0, validation: 0, documentDeletes: 0, profilePatches: [] as object[] };
  const gates: { application?: Gate; beneficiaryWrite?: Gate } = {};

  const isActive = (b: StoredRow) => Boolean(b.kinship) && b.full_name.trim() !== "";
  const memberSlots = () => {
    const activeMother = db.beneficiaries.some((b) => b.kinship === "MOTHER" && isActive(b));
    const uploaded = db.documents.some((d) => d.document_type === "MEMBER_BIRTH_CERTIFICATE" && !d.beneficiary_id);
    if (activeMother) return [...BASE_MEMBER_SLOTS, MEMBER_BIRTH_CERTIFICATE_REQUIREMENT];
    if (uploaded) return [...BASE_MEMBER_SLOTS, { ...MEMBER_BIRTH_CERTIFICATE_REQUIREMENT, required: false }];
    return BASE_MEMBER_SLOTS;
  };
  const requirements = (b: StoredRow) => {
    if (b.kinship === "MOTHER") return MOTHER_REQUIREMENTS;
    if (CHILD_KINSHIPS.has(b.kinship)) return childSlots(b.kinship, b.birth_year, db.profile.gender);
    return b.kinship ? SPOUSE_REQUIREMENTS : [];
  };
  const stored = (b: StoredRow): ApiBeneficiary => ({
    ...(b as ApiBeneficiary),
    is_active: isActive(b),
    required_documents: requirements(b),
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
    http.get(`${API}/profile/`, () => HttpResponse.json(db.profile)),
    // Like doctors/services.py: the national ID decides the gender; a contradicting typed gender
    // or an invalid mobile number is a field error and nothing is stored.
    http.patch(`${API}/profile/`, async ({ request }) => {
      const body = (await request.json()) as Partial<ApiProfile>;
      calls.profilePatches.push(body);
      const fields: Record<string, string[]> = {};
      if (body.phone_number !== undefined && !/^01[0125]\d{8}$/.test(body.phone_number)) {
        fields.phone_number = ["رقم الهاتف المحمول غير صحيح"];
      }
      if (body.national_id && body.gender && body.gender !== genderOf(body.national_id)) {
        fields.gender = ["يرجى تحديد النوع (ذكر/أنثى)"];
      }
      if (Object.keys(fields).length) {
        return HttpResponse.json(
          { error: { code: "VALIDATION_ERROR", message: "بيانات غير صحيحة", fields } },
          { status: 400 },
        );
      }
      db.profile = { ...db.profile, ...body };
      if (body.national_id) db.profile.gender = genderOf(body.national_id);
      return HttpResponse.json(db.profile);
    }),
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

async function renderForm({ withMember = false } = {}) {
  const view = renderWithProviders(
    <ApplicationFormProvider applicationId={APP_ID} options={FAST_DRAFT}>
      <DerivedQueries />
      {withMember ? <MemberSection /> : null}
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

// ---- children's slots follow the member's gender (stored by the server) ---------------------

const MALE_ID = "28506150101234"; // 13th digit 3: male
const FEMALE_ID = "28506150101244"; // 13th digit 4: female
const child = (row: number, kinship: string, name: string, birthYear: number, overrides: Partial<ApiBeneficiary> = {}) =>
  apiBeneficiary({ id: `b-${row}`, row_number: row, kinship: kinship as never, full_name: name, birth_year: birthYear, ...overrides });
/** Every child kinship, all aged 16 or more in FY 2026. */
const OLDER_CHILDREN = [
  child(1, "SON_MINOR", "عمر", 2009),
  child(2, "SON_MINOR", "مريم", 2008),
  child(3, "SON_UNIVERSITY", "يوسف", 2005),
  child(4, "SON_GRADUATE", "خالد", 2000),
];
const KINSHIP_LABEL: Record<string, string> = {
  SON_MINOR: "ابن/ابنة (18 سنة أو أقل)",
  SON_UNIVERSITY: "ابن/ابنة (طالب جامعي)",
  SON_GRADUATE: "ابن/ابنة (خريج)",
};
const groupOf = (b: ApiBeneficiary) => screen.getByRole("group", { name: `${b.full_name} — ${KINSHIP_LABEL[b.kinship]}` });
/** The state of one slot in a checklist group: missing / optional / attached, or null if not listed. */
const slotState = (group: HTMLElement, label: string) =>
  within(group).queryByText(label)?.closest("li")?.querySelector("[data-state]")?.getAttribute("data-state") ?? null;
const genderRadio = (label: "ذكر" | "أنثى") =>
  within(screen.getByRole("radiogroup", { name: "النوع :" })).getByRole("radio", { name: label });
const memberIdDigit = () =>
  within(screen.getByRole("region", { name: "بيانات العضو الأصلي" })).getByLabelText("الرقم 1 من 14");
const paperclip = (row: number) => screen.getByRole("button", { name: new RegExp(`مستندات المستفيد رقم ${row}(?!\\d)`) });

describe("children's document slots follow the member's gender", { timeout: 15_000 }, () => {
  it("male → female: every child kinship gets its birth certificate, without a reload; edits survive", async () => {
    // The graduate son is complete for a male member: both ID sides and the insurance print.
    const graduateDocs = ["BENEFICIARY_NATIONAL_ID", "BENEFICIARY_NATIONAL_ID_BACK", "INSURANCE_PRINT"].map((type, i) =>
      apiDocument({ id: `d-g${i}`, document_type: type as never, beneficiary_id: "b-4" }),
    );
    const backend = fakeBackend({
      beneficiaries: OLDER_CHILDREN,
      documents: graduateDocs,
      profile: apiProfile({ gender: "MALE", full_name: "منى حسن علي" }),
    });
    const { user } = await renderForm({ withMember: true });
    for (const b of OLDER_CHILDREN) expect(slotState(groupOf(b), BIRTH_CERTIFICATE)).toBe("optional");
    expect(paperclip(4)).toHaveAttribute("data-state", "complete");
    const before = { ...backend.calls };

    // Hold the refetch, and keep typing while it is in flight.
    backend.gates.application = gate();
    await user.click(genderRadio("أنثى"));
    await waitFor(() => expect(backend.db.profile.gender).toBe("FEMALE"));
    await waitFor(() => expect(backend.calls.application).toBe(before.application + 1));
    await user.type(screen.getByLabelText("العنوان :"), "شارع النيل");
    await user.type(nameInput(5), "سلمى");

    backend.gates.application.open();
    for (const b of OLDER_CHILDREN) {
      await waitFor(() => expect(slotState(groupOf(b), BIRTH_CERTIFICATE)).toBe("missing"));
    }
    expect(paperclip(4)).toHaveAttribute("data-state", "missing");
    expect(screen.getByLabelText("العنوان :")).toHaveValue("شارع النيل");
    expect(nameInput(5)).toHaveValue("سلمى");
    expect(backend.calls.fees).toBeGreaterThan(before.fees);
    expect(backend.calls.validation).toBeGreaterThan(before.validation);

    await user.click(paperclip(3));
    const dialog = screen.getByRole("dialog", { name: "مستندات المستفيد: يوسف" });
    expect(within(dialog).getByText(BIRTH_CERTIFICATE)).toBeInTheDocument();
    expect(backend.calls.documentDeletes).toBe(0);

    await waitFor(() => expect(backend.db.beneficiaries.map((b) => b.full_name)).toContain("سلمى"));
    await waitFor(() => expect(backend.db.profile.address).toBe("شارع النيل"));
    const settled = { ...backend.calls, profilePatches: backend.calls.profilePatches.length };
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect({ ...backend.calls, profilePatches: backend.calls.profilePatches.length }).toEqual(settled);
  });

  it("female → male: every child's certificate turns optional, uploads stay attached and visible", async () => {
    const university = child(1, "SON_UNIVERSITY", "يوسف", 2005);
    const minor = child(2, "SON_MINOR", "عمر", 2016);
    const daughter = child(3, "SON_MINOR", "مريم", 2021);
    const uploaded = apiDocument({ id: "d-bc", document_type: "BIRTH_CERTIFICATE", beneficiary_id: "b-1" });
    const backend = fakeBackend({
      beneficiaries: [university, minor, daughter],
      documents: [uploaded],
      profile: apiProfile({ gender: "FEMALE", full_name: "منى حسن علي" }),
    });
    const { user, queryClient } = await renderForm({ withMember: true });
    expect(slotState(groupOf(university), BIRTH_CERTIFICATE)).toBe("attached");
    expect(slotState(groupOf(minor), BIRTH_CERTIFICATE)).toBe("missing");
    expect(slotState(groupOf(daughter), BIRTH_CERTIFICATE)).toBe("missing");

    await user.click(genderRadio("ذكر"));

    // Below the ID age too, a male member's children need no certificate: it becomes optional …
    await waitFor(() => expect(slotState(groupOf(minor), BIRTH_CERTIFICATE)).toBe("optional"));
    expect(slotState(groupOf(daughter), BIRTH_CERTIFICATE)).toBe("optional");
    // … the 21-year-old's uploaded one stays listed and attached; both ID sides remain required …
    expect(slotState(groupOf(university), BIRTH_CERTIFICATE)).toBe("attached");
    expect(slotState(groupOf(university), "بطاقة الرقم القومي للمستفيد (وجه)")).toBe("missing");
    // … and the uploaded certificate is kept on the server and in the refetched application.
    expect(backend.db.documents).toEqual([uploaded]);
    expect(backend.calls.documentDeletes).toBe(0);
    const app = queryClient.getQueryData<{ beneficiaries: { id: string; documents: { id: string }[] }[] }>([
      "applications", "detail", APP_ID,
    ]);  // fmt: skip
    expect(app?.beneficiaries.find((b) => b.id === "b-1")?.documents.map((d) => d.id)).toEqual(["d-bc"]);
  });

  it("male → female: children below the ID age get a required certificate, without a reload", async () => {
    const minor = child(1, "SON_MINOR", "عمر", 2020);
    const university = child(2, "SON_UNIVERSITY", "يوسف", 2012);
    fakeBackend({ beneficiaries: [minor, university], profile: apiProfile({ gender: "MALE" }) });
    const { user } = await renderForm({ withMember: true });
    expect(slotState(groupOf(minor), BIRTH_CERTIFICATE)).toBe("optional");
    expect(slotState(groupOf(university), BIRTH_CERTIFICATE)).toBe("optional");
    expect(slotState(groupOf(minor), "بطاقة الرقم القومي للمستفيد (وجه)")).toBe("optional");

    await user.click(genderRadio("أنثى"));

    await waitFor(() => expect(slotState(groupOf(minor), BIRTH_CERTIFICATE)).toBe("missing"));
    expect(slotState(groupOf(university), BIRTH_CERTIFICATE)).toBe("missing");
    expect(slotState(groupOf(minor), "بطاقة الرقم القومي للمستفيد (وجه)")).toBe("optional");
  });

  it("a national ID whose stored gender differs refreshes the slots (only the ID is sent)", async () => {
    const daughter = child(1, "SON_MINOR", "مريم", 2008);
    const backend = fakeBackend({
      beneficiaries: [daughter],
      profile: apiProfile({ gender: "MALE", national_id: MALE_ID, birth_year: 1985 }),
    });
    const { user } = await renderForm({ withMember: true });
    expect(slotState(groupOf(daughter), BIRTH_CERTIFICATE)).toBe("optional");

    await user.click(memberIdDigit());
    await user.paste(FEMALE_ID);

    await waitFor(() => expect(slotState(groupOf(daughter), BIRTH_CERTIFICATE)).toBe("missing"));
    expect(backend.calls.profilePatches).toEqual([{ national_id: FEMALE_ID }]);
    expect(backend.db.profile.gender).toBe("FEMALE");
  });

  it("refreshes after a partial profile save when the persisted part changed the gender", async () => {
    const daughter = child(1, "SON_MINOR", "مريم", 2008);
    const backend = fakeBackend({
      beneficiaries: [daughter],
      profile: apiProfile({ gender: "MALE", national_id: MALE_ID, birth_year: 1985 }),
    });
    const { user } = await renderForm({ withMember: true });

    await user.type(screen.getByLabelText("المحمول :"), "123");
    await user.click(memberIdDigit());
    await user.paste(FEMALE_ID);

    // The mobile number is refused, the national ID is re-sent alone and stored as female.
    await waitFor(() => expect(backend.db.profile.national_id).toBe(FEMALE_ID));
    expect(backend.calls.profilePatches.at(-1)).toEqual({ national_id: FEMALE_ID });
    expect(backend.calls.profilePatches.some((body) => "phone_number" in body)).toBe(true);
    await waitFor(() => expect(slotState(groupOf(daughter), BIRTH_CERTIFICATE)).toBe("missing"));
    expect(screen.getByText("رقم الهاتف المحمول غير صحيح")).toBeInTheDocument();
  });

  it("does not refetch the application for profile edits that cannot change the slots", async () => {
    const backend = fakeBackend({
      beneficiaries: [child(1, "SON_MINOR", "مريم", 2008)],
      profile: apiProfile({ gender: "MALE" }),
    });
    const { user } = await renderForm({ withMember: true });
    await waitFor(() => expect(backend.calls.fees).toBe(1));
    const before = { ...backend.calls };

    await user.type(screen.getByLabelText("العنوان :"), "شارع النيل");
    await waitFor(() => expect(backend.db.profile.address).toBe("شارع النيل"));
    await waitFor(() => expect(backend.calls.fees).toBeGreaterThan(before.fees));
    expect(backend.calls.validation).toBeGreaterThan(before.validation);
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(backend.calls.application).toBe(before.application);
  });
});
