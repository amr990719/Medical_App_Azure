import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import {
  API,
  APP_ID,
  apiApplication,
  apiBeneficiary,
  apiDocument,
  CHILD_REQUIREMENTS,
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
const inactive = apiBeneficiary({ id: "b-x", row_number: 3, kinship: "DAUGHTER", full_name: "", is_active: false });

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
    expect(item(member, "صورة العضو الأصلي")).toHaveTextContent("اختياري");
    expect(within(member).queryByText("إيصال الدفع")).toBeNull(); // step 4 has its own page
  });

  it("lists every active beneficiary with the documents its kinship and age need", async () => {
    await renderInForm(<DocumentsChecklist />, { app });
    const group = screen.getByRole("group", { name: "عمر أحمد محمد — ابن (18 سنة أو أقل)" });
    expect(item(group, "شهادة الميلاد")).toHaveTextContent("غير مرفق");
    expect(item(group, "بطاقة الرقم القومي")).toHaveTextContent("اختياري");
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
    const input = screen.getByLabelText("رفع شهادة الميلاد", { selector: "input" });
    await user.upload(input, new File(["png"], "birth.png", { type: "image/png" }));
    await waitFor(() => expect(form).not.toBeNull());
    expect(form!.get("document_type")).toBe("BIRTH_CERTIFICATE");
    expect(form!.get("beneficiary_id")).toBe("b-son");
  });
});
