import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  APP_ID,
  apiApplication,
  apiProfile,
  cleanValidation,
  draftHandlers,
  handlers,
  meDoctor,
  type ApiApplication,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function serve(app: ApiApplication, validation: object = cleanValidation) {
  server.use(
    handlers.me(meDoctor),
    handlers.referenceData(),
    draftHandlers.application(app),
    draftHandlers.profile(apiProfile({ full_name: "أحمد محمد علي حسن" })),
    draftHandlers.validation(app.id, validation),
  );
}

describe("PrintPage (PROMPT.md §9.8)", () => {
  it("prints the sheet with the reference number and submission date, the full table and no attachments panel", async () => {
    serve(
      apiApplication({
        status: "SUBMITTED",
        is_editable: false,
        reference_number: "MED-2026-000123",
        submitted_at: "2026-10-03T09:15:00+03:00",
      }),
    );
    renderApp(`/application/${APP_ID}/print`);
    expect(await screen.findByText("MED-2026-000123")).toBeInTheDocument();
    expect(screen.getByText("٣ أكتوبر ٢٠٢٦")).toBeInTheDocument();
    expect(await screen.findByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" })).toBeInTheDocument();
    expect(screen.queryByText("مرفقات العضو الأصلي الإلزامية")).toBeNull();
    expect(screen.getByLabelText("أسم العضو :")).toHaveAttribute("readonly");
  });

  it("omits the reference line for a draft and prints on demand", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    serve(apiApplication());
    const { user } = renderApp(`/application/${APP_ID}/print`);
    await screen.findByRole("heading", { name: "استمارة اشتراك بمشروع العلاج" });
    expect(screen.queryByText("رقم الطلب :")).toBeNull();
    await user.click(screen.getByRole("button", { name: "طباعة" }));
    expect(print).toHaveBeenCalled();
  });
});

describe("ApplicationRedirectPage (/application/:id)", () => {
  it("opens the form while steps 1–3 are incomplete", async () => {
    serve(apiApplication(), { ...cleanValidation, steps_complete: { "1": false, "2": true, "3": false, "4": false, "5": false } });
    const { router } = renderApp(`/application/${APP_ID}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/form`));
  });

  it("opens the receipt step when the form is complete", async () => {
    serve(apiApplication());
    const { router } = renderApp(`/application/${APP_ID}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/payment`));
  });

  it("opens the review when the receipt is uploaded too", async () => {
    serve(apiApplication(), { ...cleanValidation, steps_complete: { "1": true, "2": true, "3": true, "4": true, "5": false } });
    const { router } = renderApp(`/application/${APP_ID}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/review`));
  });

  it("opens the status page for a submitted application", async () => {
    serve(apiApplication({ status: "UNDER_REVIEW", is_editable: false, reference_number: "MED-2026-000001" }));
    const { router } = renderApp(`/application/${APP_ID}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/status`));
  });
});
