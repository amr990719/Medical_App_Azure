/**
 * The member's own photo (PERSONAL_PHOTO) is required for a FIRST_TIME application only. The rule
 * lives on the server (`member_required_documents`); the checklist must follow an application
 * type change without a reload, and an uploaded photo stays attached when it becomes optional.
 */
import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { DocumentsChecklist } from "@/features/documents/DocumentsChecklist";
import { useValidation } from "@/features/applications/useValidation";
import { API, APP_ID, apiApplication, apiDocument, apiProfile, cleanValidation, feeQuote, type ApiDocument } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { FAST_DRAFT } from "@/test/renderForm";
import { server } from "@/test/server";
import { ApplicationFormProvider } from "./ApplicationFormProvider";
import { FormHeader } from "./FormHeader";

const PHOTO = "صورة العضو الأصلي";
const PHOTO_ERROR = { step: 3, field: "documents.PERSONAL_PHOTO", code: "MISSING_DOCUMENT", message: "يرجى إرفاق صورة العضو الأصلي" };

function fakeBackend({ applicationType = "FIRST_TIME", documents = [] as ApiDocument[] } = {}) {
  const db = { applicationType, documents };
  const calls = { applicationPatches: [] as object[], validation: 0, deletes: 0 };
  const photoMissing = () =>
    db.applicationType === "FIRST_TIME" && !db.documents.some((d) => d.document_type === "PERSONAL_PHOTO");
  const snapshot = () => {
    const base = apiApplication();
    return apiApplication({
      application_type: db.applicationType as never,
      documents: db.documents,
      member_required_documents: base.member_required_documents.map((slot) =>
        (slot as { type: string }).type === "PERSONAL_PHOTO"
          ? { ...slot, required: db.applicationType === "FIRST_TIME" }
          : slot,
      ),
    });
  };
  const base = `${API}/applications/${APP_ID}`;
  server.use(
    http.get(`${API}/profile/`, () => HttpResponse.json(apiProfile())),
    http.get(`${base}/`, () => HttpResponse.json(snapshot())),
    http.patch(`${base}/`, async ({ request }) => {
      const body = (await request.json()) as { application_type?: string };
      calls.applicationPatches.push(body);
      if (body.application_type) db.applicationType = body.application_type;
      return HttpResponse.json(snapshot());
    }),
    http.get(`${base}/fees/`, () => HttpResponse.json(feeQuote)),
    http.get(`${base}/validation/`, () => {
      calls.validation += 1;
      return HttpResponse.json(
        photoMissing() ? { ...cleanValidation, is_valid: false, errors: [PHOTO_ERROR] } : cleanValidation,
      );
    }),
    http.delete(`${API}/documents/:id/`, () => {
      calls.deletes += 1;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { db, calls };
}

function Validation() {
  const validation = useValidation(APP_ID);
  return <output data-testid="validation">{validation.data?.errors.map((e) => e.field).join(",") ?? ""}</output>;
}

async function renderForm() {
  const view = renderWithProviders(
    <ApplicationFormProvider applicationId={APP_ID} options={FAST_DRAFT}>
      <Validation />
      <FormHeader />
      <DocumentsChecklist />
    </ApplicationFormProvider>,
  );
  await screen.findByRole("group", { name: "العضو الأصلي" });
  return view;
}

const photoState = () =>
  within(screen.getByRole("group", { name: "العضو الأصلي" }))
    .getByText(PHOTO)
    .closest("li")
    ?.querySelector("[data-state]")
    ?.getAttribute("data-state");
const typeRadio = (label: "أول مرة" | "إضافة") =>
  within(screen.getByRole("radiogroup", { name: "نوع الطلب :" })).getByRole("radio", { name: label });

describe("the member photo follows the application type (FIRST_TIME only)", { timeout: 15_000 }, () => {
  it("FIRST_TIME → ADDITION → FIRST_TIME refreshes the requirement and validation without a reload", async () => {
    const { calls } = fakeBackend();
    const { user } = await renderForm();
    expect(photoState()).toBe("missing");
    await waitFor(() => expect(screen.getByTestId("validation")).toHaveTextContent("documents.PERSONAL_PHOTO"));

    await user.click(typeRadio("إضافة"));
    await waitFor(() => expect(photoState()).toBe("optional"));
    await waitFor(() => expect(screen.getByTestId("validation")).toBeEmptyDOMElement());
    expect(calls.applicationPatches).toEqual([{ application_type: "ADDITION" }]);

    await user.click(typeRadio("أول مرة"));
    await waitFor(() => expect(photoState()).toBe("missing"));
    await waitFor(() => expect(screen.getByTestId("validation")).toHaveTextContent("documents.PERSONAL_PHOTO"));
  });

  it("keeps an uploaded photo attached when it becomes optional", async () => {
    const photo = apiDocument({ id: "d-photo", document_type: "PERSONAL_PHOTO", beneficiary_id: null });
    const { db, calls } = fakeBackend({ documents: [photo] });
    const { user } = await renderForm();
    expect(photoState()).toBe("attached");

    await user.click(typeRadio("إضافة"));
    await waitFor(() => expect(db.applicationType).toBe("ADDITION"));
    await waitFor(() => expect(photoState()).toBe("attached"));
    expect(screen.getByRole("img", { name: "صورة العضو الأصلي" })).toBeInTheDocument(); // still in the photo box
    expect(db.documents).toEqual([photo]);
    expect(calls.deletes).toBe(0);
  });
});
