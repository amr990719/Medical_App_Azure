import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
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
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const receipt = apiDocument({ id: "d-r", document_type: "PAYMENT_RECEIPT" });
const ready = apiApplication({
  payment_status: "PENDING_REVIEW",
  documents: [receipt],
  declaration_name: "أحمد محمد علي حسن",
});
const readyValidation = { ...cleanValidation, steps_complete: { "1": true, "2": true, "3": true, "4": true, "5": false } };

function serve(app: ApiApplication = ready, validation: object = readyValidation) {
  server.use(
    handlers.me(meDoctor),
    handlers.referenceData(),
    draftHandlers.application(app),
    draftHandlers.profile(apiProfile({ full_name: "أحمد محمد علي حسن" })),
    draftHandlers.fees(app.id),
    draftHandlers.validation(app.id, validation),
  );
}

async function openReview() {
  const view = renderApp(`/application/${APP_ID}/review`);
  await screen.findByRole("heading", { name: "المراجعة والتقديم" });
  return view;
}

describe("ReviewPage (PROMPT.md §8, §9.7, §16.2)", () => {
  it("shows the whole form read-only, the fee summary and the server's readiness", async () => {
    serve();
    await openReview();
    expect(await screen.findByLabelText("أسم العضو :")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("اسم المقر")).toHaveValue("أحمد محمد علي حسن");
    expect(await screen.findByText("الاستمارة مكتملة وجاهزة للتقديم.")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "مسح تلقائي" })).toBeNull();
  });

  it("lists the server validation errors with a way back to the form", async () => {
    serve(ready, {
      ...cleanValidation,
      is_valid: false,
      errors: [{ step: 1, field: "member.phone_number", code: "INVALID", message: "رقم الهاتف المحمول غير صحيح" }],
    });
    await openReview();
    const title = await screen.findByText("يرجى تصحيح الأخطاء التالية قبل المتابعة:");
    expect(title.closest("[role=alert]")).toHaveTextContent("رقم الهاتف المحمول غير صحيح");
    expect(screen.getByRole("link", { name: "الذهاب لتصحيح الاستمارة" })).toHaveAttribute(
      "href",
      `/application/${APP_ID}/form`,
    );
    expect(screen.getByRole("button", { name: "تقديم الطلب" })).toBeDisabled();
  });

  it("requires the explicit acceptance before submitting, and stores it on the server", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/applications/${APP_ID}/`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...ready, declaration_accepted: true, declaration_accepted_at: "2026-10-06T10:00:00+03:00" });
      }),
    );
    serve();
    const { user } = await openReview();
    const submit = screen.getByRole("button", { name: "تقديم الطلب" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "أقر بأن جميع البيانات صحيحة وأوافق على نص الإقرار." }));
    await waitFor(() => expect(bodies).toEqual([{ declaration_accepted: true }]));
    await waitFor(() => expect(submit).toBeEnabled());
  });

  it("submits and shows the reference number", async () => {
    const accepted = { ...ready, declaration_accepted: true, declaration_accepted_at: "2026-10-06T10:00:00+03:00" };
    const submitted = {
      ...accepted,
      status: "SUBMITTED" as const,
      is_editable: false,
      reference_number: "MED-2026-000042",
      submitted_at: "2026-10-06T10:05:00+03:00",
      fee_snapshot: { total: 3025 },
    };
    serve(accepted);
    server.use(
      http.post(`${API}/applications/${APP_ID}/submit/`, () => {
        server.use(draftHandlers.application(submitted));
        return HttpResponse.json(submitted);
      }),
      http.get(`${API}/applications/`, () => HttpResponse.json({ count: 1, next: null, previous: null, results: [submitted] })),
    );
    const { user, router } = await openReview();
    await user.click(screen.getByRole("button", { name: "تقديم الطلب" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/status`));
    expect(await screen.findByText("تم تقديم طلبك بنجاح")).toBeInTheDocument();
    expect(screen.getByText("MED-2026-000042")).toBeInTheDocument();
  });

  it("shows every error the submit endpoint returns", async () => {
    const accepted = { ...ready, declaration_accepted: true, declaration_accepted_at: "2026-10-06T10:00:00+03:00" };
    serve(accepted);
    server.use(
      http.post(`${API}/applications/${APP_ID}/submit/`, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "يرجى تصحيح الأخطاء",
              fields: {},
              errors: [
                { step: 4, field: "receipt", code: "MISSING_RECEIPT", message: "يرجى رفع إيصال الدفع" },
                { step: 5, field: "declaration.name", code: "MISMATCH", message: "اسم المقر يجب أن يطابق اسم العضو" },
              ],
            },
          },
          { status: 400 },
        ),
      ),
    );
    const { user } = await openReview();
    await user.click(screen.getByRole("button", { name: "تقديم الطلب" }));
    const title = await screen.findByText("يرجى تصحيح الأخطاء التالية قبل المتابعة:");
    const panel = title.closest("[role=alert]") as HTMLElement;
    expect(within(panel).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "يرجى رفع إيصال الدفع",
      "اسم المقر يجب أن يطابق اسم العضو",
    ]);
  });

  it("calls it resubmission after a correction request", async () => {
    serve({ ...ready, status: "NEEDS_CORRECTION", reference_number: "MED-2026-000042" });
    await openReview();
    expect(screen.getByRole("button", { name: "إعادة تقديم الطلب" })).toBeInTheDocument();
  });
});
