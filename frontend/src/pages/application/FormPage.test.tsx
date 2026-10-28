import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
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
        "وأقر بالموافقة على النظام العلاجي الذي يسير عليه المشروع وكذلك أية تعديلات تتم أثناء العام تصدر من إدارة المشروع، وأتبرع تكافلا بمبلغ اشتراكي لعلاج زملائي المشتركين وأتعاون معهم في سداد قيمة العلاج .",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("المقر بما فيه")).not.toBeInTheDocument();
    expect(screen.queryByText(/اضغط مسح تلقائي لاستخراج البيانات/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "مرفقات العضو الأصلي الإلزامية" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" })).toHaveTextContent(
      "3٬025 ج.م",
    );
    const bar = screen.getByRole("toolbar", { name: "إجراءات الاستمارة" });
    expect(within(bar).getByRole("button", { name: "تسجيل الخروج" })).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: "طباعة" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "طباعة الاستمارة" })).not.toBeInTheDocument();
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

  it("scrolls to the error summary once per failed continue, never while the errors are corrected", async () => {
    const issue = (field: string, message: string) => ({ step: 1, field, code: "X", message });
    const failing = (errors: object[]) => ({
      ...cleanValidation,
      is_valid: false,
      errors,
      steps_complete: { "1": false, "2": true, "3": true, "4": false, "5": false },
    });
    let current: object = failing([
      issue("member.address", "يرجى إدخال العنوان"),
      issue("member.syndicate_type", "يرجى اختيار نوع النقابة"),
    ]);
    let validationRequests = 0;
    serve();
    server.use(
      http.get(`${API}/applications/${APP_ID}/validation/`, () => {
        validationRequests += 1;
        return HttpResponse.json(current);
      }),
      http.patch(`${API}/profile/`, () => {
        // The server now accepts the address: the next validation lists one error fewer.
        current = failing([issue("member.syndicate_type", "يرجى اختيار نوع النقابة")]);
        return HttpResponse.json(apiProfile({ address: "شارع" }));
      }),
      http.get(`${API}/applications/`, () => HttpResponse.json({ count: 0, next: null, previous: null, results: [] })),
    );
    const scroll = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    const { user, router } = await openForm();
    expect(scroll).not.toHaveBeenCalled();

    // 1. A failed continue scrolls to the summary, once, after it is rendered.
    const continueButton = screen.getByRole("button", { name: "متابعة لرفع الإيصال" });
    await user.click(continueButton);
    const box = (await screen.findByText("يرجى تصحيح الأخطاء التالية قبل المتابعة:")).closest("[role=alert]") as HTMLElement;
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
    expect(scroll.mock.contexts[0]).toBe(box);
    expect(within(box).getAllByRole("listitem")).toHaveLength(2);

    // 2. Correcting a field: autosave, refetched validation and a shorter list — no scroll, focus kept.
    const address = screen.getByLabelText("العنوان :");
    const before = validationRequests;
    await user.type(address, "شارع");
    await waitFor(() => expect(within(box).getAllByRole("listitem")).toHaveLength(1), { timeout: 3000 });
    expect(validationRequests).toBeGreaterThan(before);
    expect(address).toHaveFocus();
    expect(scroll).toHaveBeenCalledTimes(1);

    // 3. Another failed continue scrolls to the updated summary again.
    await user.click(continueButton);
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(2));
    expect(router.state.location.pathname).toBe(`/application/${APP_ID}/form`);

    // 4. Once the errors are fixed, continuing proceeds to the receipt page.
    current = cleanValidation;
    await user.click(continueButton);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/payment`));
    expect(scroll).toHaveBeenCalledTimes(2);
    scroll.mockRestore();
  }, 15_000);

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
