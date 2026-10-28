import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import {
  API,
  APP_ID,
  apiApplication,
  apiBeneficiary,
  apiDocument,
  apiReferenceData,
  CHILD_REQUIREMENTS,
  MEMBER_BIRTH_CERTIFICATE_REQUIREMENT,
  MOTHER_REQUIREMENTS,
  PHOTO_CHILD_EXEMPT_HINT,
  PHOTO_HINT,
  photoRequirement,
} from "@/test/fixtures";
import { renderInForm } from "@/test/renderForm";
import { server } from "@/test/server";
import { DocumentsChecklist } from "./DocumentsChecklist";

const son = apiBeneficiary({
  id: "b-son",
  row_number: 2,
  kinship: "SON_MINOR",
  full_name: "عمر أحمد محمد",
  birth_year: 2015,
  required_documents: CHILD_REQUIREMENTS,
});
const inactive = apiBeneficiary({ id: "b-x", row_number: 3, kinship: "SON_MINOR", full_name: "", is_active: false });

const app = apiApplication({
  documents: [apiDocument({ id: "d-front", document_type: "NATIONAL_ID_FRONT" })],
  beneficiaries: [son, inactive],
});

function item(group: HTMLElement, label: string) {
  return within(group).getByText(label).closest("li") as HTMLElement;
}

describe("DocumentsChecklist (PROMPT.md §9.6)", () => {
  it("lists the member documents from the rules table with their status", async () => {
    await renderInForm(<DocumentsChecklist />, { app });
    const member = screen.getByRole("group", { name: "العضو الأصلي" });
    expect(item(member, "صورة البطاقة (وجه)")).toHaveTextContent("✓ مرفق");
    expect(item(member, "صورة البطاقة (ظهر)")).toHaveTextContent("غير مرفق");
    expect(item(member, "كارنيه النقابة")).toHaveTextContent("غير مرفق");
    expect(item(member, "صورة العضو الأصلي")).toHaveTextContent("غير مرفق"); // FIRST_TIME: required
    expect(within(member).queryByText("إيصال الدفع")).toBeNull(); // step 4 has its own page
  });

  it("shows the member photo as optional when the server says so (ADDITION application)", async () => {
    const addition = {
      ...app,
      application_type: "ADDITION" as const,
      member_required_documents: app.member_required_documents.map((slot) =>
        (slot as { type: string }).type === "PERSONAL_PHOTO" ? { ...slot, required: false } : slot,
      ),
    };
    await renderInForm(<DocumentsChecklist />, { app: addition });
    const member = screen.getByRole("group", { name: "العضو الأصلي" });
    expect(item(member, "صورة العضو الأصلي")).toHaveTextContent("اختياري");
  });

  it("lists every active beneficiary with the documents its kinship and age need", async () => {
    await renderInForm(<DocumentsChecklist />, { app });
    const group = screen.getByRole("group", { name: "عمر أحمد محمد — ابن/ابنة (18 سنة أو أقل)" });
    expect(item(group, "شهادة ميلاد المستفيد")).toHaveTextContent("غير مرفق");
    expect(item(group, "بطاقة الرقم القومي للمستفيد (وجه)")).toHaveTextContent("اختياري");
    expect(item(group, "بطاقة الرقم القومي للمستفيد (ظهر)")).toHaveTextContent("اختياري");
    const photo = item(group, "صورة شخصية للمستفيد بخلفية بيضاء");
    expect(photo).toHaveTextContent(PHOTO_HINT);
    expect(photo).toHaveTextContent(PHOTO_CHILD_EXEMPT_HINT);
    expect(screen.getAllByRole("group")).toHaveLength(2); // the nameless row is not active
  });

  it("uploads a missing document from its row", async () => {
    let form: FormData | null = null;
    server.use(
      http.post(`${API}/applications/${APP_ID}/documents/`, async ({ request }) => {
        form = await request.formData();
        return HttpResponse.json(apiDocument({ id: "d-b", document_type: "BIRTH_CERTIFICATE", beneficiary_id: "b-son" }), {
          status: 201,
        });
      }),
    );
    const { user } = await renderInForm(<DocumentsChecklist />, { app });
    const input = screen.getByLabelText("رفع شهادة ميلاد المستفيد", { selector: "input" });
    await user.upload(input, new File(["png"], "birth.png", { type: "image/png" }));
    await waitFor(() => expect(form).not.toBeNull());
    expect(form!.get("document_type")).toBe("BIRTH_CERTIFICATE");
    expect(form!.get("beneficiary_id")).toBe("b-son");
  });

  it("adds the member's own birth certificate to the member group while a mother is listed", async () => {
    const mother = apiBeneficiary({
      id: "b-mother",
      row_number: 1,
      kinship: "MOTHER",
      full_name: "فاطمة علي أحمد",
      birth_year: 1960,
      required_documents: MOTHER_REQUIREMENTS,
      documents: [apiDocument({ id: "d-mb", document_type: "BIRTH_CERTIFICATE", beneficiary_id: "b-mother" })],
    });
    const withMother = apiApplication({
      beneficiaries: [mother],
      member_required_documents: [
        ...(apiReferenceData.document_rules.member as unknown as Record<string, unknown>[]),
        MEMBER_BIRTH_CERTIFICATE_REQUIREMENT,
      ],
    });
    await renderInForm(<DocumentsChecklist />, { app: withMother });
    const member = screen.getByRole("group", { name: "العضو الأصلي" });
    // The mother's certificate (uploaded on her row) does not count for the member's slot.
    expect(item(member, "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم")).toHaveTextContent("غير مرفق");
    const motherGroup = screen.getByRole("group", { name: "فاطمة علي أحمد — أم" });
    expect(item(motherGroup, "بطاقة الرقم القومي للمستفيد (وجه)")).toHaveTextContent("غير مرفق");
    expect(item(motherGroup, "بطاقة الرقم القومي للمستفيد (ظهر)")).toHaveTextContent("غير مرفق");
  });

  it("sends the member birth certificate without a beneficiary", async () => {
    let form: FormData | null = null;
    server.use(
      http.post(`${API}/applications/${APP_ID}/documents/`, async ({ request }) => {
        form = await request.formData();
        return HttpResponse.json(apiDocument({ id: "d-mbc", document_type: "MEMBER_BIRTH_CERTIFICATE" }), { status: 201 });
      }),
    );
    const withMother = apiApplication({
      member_required_documents: [MEMBER_BIRTH_CERTIFICATE_REQUIREMENT],
    });
    const { user } = await renderInForm(<DocumentsChecklist />, { app: withMother });
    const input = screen.getByLabelText("رفع شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم", { selector: "input" });
    await user.upload(input, new File(["png"], "me.png", { type: "image/png" }));
    await waitFor(() => expect(form).not.toBeNull());
    expect(form!.get("document_type")).toBe("MEMBER_BIRTH_CERTIFICATE");
    expect(form!.get("beneficiary_id")).toBeNull();
  });

  it("keeps the beneficiary photo image-only even when PDF documents are enabled", async () => {
    server.use(
      http.get(`${API}/reference-data/`, () =>
        HttpResponse.json({
          ...apiReferenceData,
          features: { ...apiReferenceData.features, allow_pdf: true },
          upload: {
            ...apiReferenceData.upload,
            accepted_content_types: [...apiReferenceData.upload.accepted_content_types, "application/pdf"],
          },
        }),
      ),
    );
    const firstTime = apiBeneficiary({ required_documents: [photoRequirement(true)], is_first_time: true });
    await renderInForm(<DocumentsChecklist />, { app: apiApplication({ beneficiaries: [firstTime] }) });
    const photo = await screen.findByLabelText("رفع صورة شخصية للمستفيد بخلفية بيضاء", { selector: "input" });
    await waitFor(() => expect(photo).toHaveAttribute("accept", "image/jpeg,image/png,image/webp"));
    const back = screen.queryByLabelText("رفع بطاقة الرقم القومي للمستفيد (ظهر)", { selector: "input" });
    expect(back).toBeNull();
  });
});
