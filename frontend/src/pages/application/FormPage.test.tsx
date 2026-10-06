import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { draftDefaults } from "@/features/application-form/draftController";
import {
  API,
  APP_ID,
  apiApplication,
  apiDocument,
  apiProfile,
  cleanValidation,
  draftHandlers,
  handlers,
  meDoctor,
  type ApiApplication,
  type ApiProfile,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function serve(app: ApiApplication = apiApplication(), profile: ApiProfile = apiProfile(), validation: object = cleanValidation) {
  server.use(
    handlers.me(meDoctor),
    handlers.referenceData(),
    draftHandlers.application(app),
    draftHandlers.profile(profile),
    draftHandlers.fees(app.id),
    draftHandlers.validation(app.id, validation),
  );
}

async function openForm(path = `/application/${APP_ID}/form`) {
  const view = renderApp(path);
  await screen.findByRole("heading", { name: "استمارة اشتراك بمشروع العلاج" });
  return view;
}

const realDefaults = { ...draftDefaults };
beforeAll(() => Object.assign(draftDefaults, { debounceMs: 20, retryDelays: [5, 10, 20] }));
afterAll(() => Object.assign(draftDefaults, realDefaults));

describe("FormPage (PROMPT.md §9)", () => {
  it("shows the paper form, the declaration text exactly and the fiscal-year fee summary", async () => {
    serve();
    await openForm();
    expect(screen.getByText("استمارة اشتراك — 2026")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "مراحل الاستمارة" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "إقــــــــرار" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "مع العلم انه لا يجوز استفادة الابن بعد التخرج أو الابنة بعد الزواج واذا ثبت عكس ذلك أتحمل المسئولية المالية والقانونية فورا مع عدم رد قيمة الاشتراك وتحمل كافة التكاليف وللمشروع الحق في اتخاذ اي اجراء مناسب لذلك .",
      ).tagName,
    ).toBe("U");
    expect(screen.getByText("المقر بما فيه")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" })).toHaveTextContent(
      "3٬025 ج.م",
    );
    const bar = screen.getByRole("toolbar", { name: "إجراءات الاستمارة" });
    expect(within(bar).getByRole("button", { name: "تسجيل الخروج" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "طباعة" })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "متابعة لرفع الإيصال" })).toBeInTheDocument();
  });

  it("shows the autosave states: saving, then saved", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.patch(`${API}/profile/`, async () => {
        await held;
        return HttpResponse.json(apiProfile({ address: "شارع" }));
      }),
    );
    serve();
    const { user } = await openForm();
    await user.type(screen.getByLabelText("العنوان :"), "شارع");
    expect(await screen.findByText("جارٍ الحفظ…", {}, { timeout: 3000 })).toBeInTheDocument();
    release();
    expect(await screen.findByText("تم الحفظ")).toBeInTheDocument();
  });

  it("offers a retry when saving failed", async () => {
    let fail = true;
    server.use(
      http.patch(`${API}/profile/`, () =>
        fail
          ? HttpResponse.json({ error: { code: "SERVER_ERROR", message: "x", fields: {} } }, { status: 500 })
          : HttpResponse.json(apiProfile({ address: "شارع" })),
      ),
    );
    serve();
    const { user } = await openForm();
    await user.type(screen.getByLabelText("العنوان :"), "ش");
    const retry = await screen.findByRole("button", { name: "تعذّر الحفظ — إعادة المحاولة" }, { timeout: 3000 });
    fail = false;
    await user.click(retry);
    expect(await screen.findByText("تم الحفظ")).toBeInTheDocument();
  });

  it("merges OCR suggestions from the ID front into empty fields only", async () => {
    const front = apiDocument({ id: "d-front", document_type: "NATIONAL_ID_FRONT" });
    server.use(
      http.post(`${API}/applications/${APP_ID}/documents/`, () => HttpResponse.json(front, { status: 201 })),
      http.post(`${API}/documents/d-front/extract/`, () =>
        HttpResponse.json({
          document_id: "d-front",
          document_type: "NATIONAL_ID_FRONT",
          fields: { member_name: "أحمد محمد علي حسن", national_id: "28506150101234", birth_year: 1985, address: "١٢ شارع عباس العقاد" },
        }),
      ),
      http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())),
    );
    serve(apiApplication(), apiProfile({ address: "عنوان كتبه الطبيب" }));
    const { user } = await openForm();

    const slot = screen.getByRole("group", { name: "صورة البطاقة (وجه)" });
    await user.upload(within(slot).getByLabelText("صورة البطاقة (وجه)"), new File(["x"], "front.png", { type: "image/png" }));
    await user.click(await within(slot).findByRole("button", { name: "مسح تلقائي" }));

    expect(await screen.findByText("✓ تم استخراج البيانات — راجع الحقول أدناه وعدّل إن لزم")).toBeInTheDocument();
    expect(screen.getByLabelText("أسم العضو :")).toHaveValue("أحمد محمد علي حسن");
    expect(screen.getByLabelText("سنة الميلاد :")).toHaveValue("1985");
    expect(screen.getByLabelText("العنوان :")).toHaveValue("عنوان كتبه الطبيب");
    expect(screen.getByRole("radio", { name: "ذكر" })).toBeChecked();
  });

  it("continuing with errors shows every step 1–3 message in the panel and inline, and stays", async () => {
    const issue = (step: number, field: string, message: string) => ({ step, field, code: "X", message });
    const errors = [
      issue(1, "member.syndicate_type", "يرجى اختيار نوع النقابة"),
      issue(1, "member.full_name", "اسم العضو يجب أن يكون 5 أحرف على الأقل"),
      issue(3, "documents.NATIONAL_ID_FRONT", "يرجى إرفاق صورة وجه البطاقة الشخصية"),
      issue(5, "declaration.name", "اسم المقر يجب أن يطابق اسم العضو"),
    ];
    serve(apiApplication(), apiProfile(), {
      ...cleanValidation,
      is_valid: false,
      errors,
      steps_complete: { "1": false, "2": true, "3": false, "4": false, "5": false },
    });
    const { user, router } = await openForm();
    await user.click(screen.getByRole("button", { name: "متابعة لرفع الإيصال" }));

    const title = await screen.findByText("يرجى تصحيح الأخطاء التالية قبل المتابعة:");
    const box = title.closest("[role=alert]") as HTMLElement;
    expect(within(box).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "يرجى اختيار نوع النقابة",
      "اسم العضو يجب أن يكون 5 أحرف على الأقل",
      "يرجى إرفاق صورة وجه البطاقة الشخصية",
    ]);
    // inline, under the fields (the declaration error is shown inline but does not block step 4)
    expect(screen.getByLabelText("أسم العضو :")).toHaveAccessibleDescription("اسم العضو يجب أن يكون 5 أحرف على الأقل");
    expect(screen.getByLabelText("اسم المقر")).toHaveAccessibleDescription("اسم المقر يجب أن يطابق اسم العضو");
    expect(router.state.location.pathname).toBe(`/application/${APP_ID}/form`);
  });

  it("continuing with steps 1–3 complete opens the receipt page", async () => {
    serve();
    server.use(
      http.get(`${API}/applications/`, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    );
    const { user, router } = await openForm();
    await user.click(screen.getByRole("button", { name: "متابعة لرفع الإيصال" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/payment`));
  });

  it("is read-only for a submitted application", async () => {
    serve(apiApplication({ status: "SUBMITTED", is_editable: false, reference_number: "MED-2026-000001" }));
    await openForm();
    expect(screen.getByText("هذا الطلب مقدم ولا يمكن تعديله الآن.")).toBeInTheDocument();
    expect(screen.getByLabelText("العنوان :")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("اسم المقر")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "متابعة لرفع الإيصال" })).toBeNull();
    expect(screen.queryByRole("button", { name: "مسح تلقائي" })).toBeNull();
  });

  it("shows the reviewer's notes when a correction was requested", async () => {
    serve(apiApplication({ status: "NEEDS_CORRECTION", reference_number: "MED-2026-000001", review_notes: "صورة البطاقة غير واضحة" }));
    await openForm();
    expect(screen.getByText("صورة البطاقة غير واضحة")).toBeInTheDocument();
  });
});
