import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import {
  API,
  apiApplication,
  handlers,
  meDoctor,
  submittedApplication,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function setup(apps = [apiApplication()]) {
  server.use(handlers.me(meDoctor), handlers.referenceData(), handlers.applications(apps));
  return renderApp("/dashboard");
}

const card = (name: RegExp | string) => screen.getByRole("article", { name });

describe("DashboardPage", () => {
  it("greets the doctor by first name", async () => {
    setup([]);
    expect(await screen.findByRole("heading", { name: "مرحباً د. أحمد" })).toBeInTheDocument();
  });

  it("shows the empty state with a call to action", async () => {
    setup([]);
    expect(await screen.findByText("لم تقدم أي طلبات بعد")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "تقديم طلب جديد" })).toBeEnabled();
  });

  it("shows a draft card with status, last save and a continue link", async () => {
    const draft = apiApplication();
    setup([draft]);
    const article = await screen.findByRole("article", { name: "مسودة — السنة المالية 2026" });
    expect(within(article).getByText("مسودة").closest("[data-status]")).toHaveAttribute("data-status", "DRAFT");
    expect(within(article).getByText(/^آخر حفظ:/)).toBeInTheDocument();
    expect(within(article).getByRole("link", { name: "متابعة" })).toHaveAttribute(
      "href",
      `/application/${draft.id}`,
    );
  });

  it("shows a submitted card with reference number, date and total", async () => {
    setup([submittedApplication]);
    await screen.findByRole("article", { name: "MED-2026-000123" });
    const article = card("MED-2026-000123");
    expect(within(article).getByText("قيد المراجعة")).toBeInTheDocument();
    expect(within(article).getByText("٣ أكتوبر ٢٠٢٦", { exact: false })).toBeInTheDocument();
    expect(within(article).getByText("3٬025 ج.م")).toBeInTheDocument();
    expect(within(article).getByRole("link", { name: "عرض" })).toHaveAttribute(
      "href",
      `/application/${submittedApplication.id}/status`,
    );
  });

  it("highlights review notes and offers correction for NEEDS_CORRECTION", async () => {
    const app = apiApplication({
      ...submittedApplication,
      status: "NEEDS_CORRECTION",
      review_notes: "صورة البطاقة غير واضحة",
      is_editable: true,
    });
    setup([app]);
    const article = await screen.findByRole("article", { name: "MED-2026-000123" });
    expect(within(article).getByText("صورة البطاقة غير واضحة")).toBeVisible();
    expect(within(article).getByRole("link", { name: "تصحيح وإعادة التقديم" })).toHaveAttribute(
      "href",
      `/application/${app.id}/form`,
    );
  });

  it("disables a new application while one is active this fiscal year", async () => {
    setup([apiApplication()]);
    await screen.findByRole("article", { name: "مسودة — السنة المالية 2026" });
    expect(screen.getByRole("button", { name: "تقديم طلب جديد" })).toBeDisabled();
    expect(screen.getByText("لديك طلب نشط للسنة المالية 2026. يمكنك متابعته من القائمة.")).toBeInTheDocument();
  });

  it("allows a new application when the only one was rejected", async () => {
    setup([apiApplication({ ...submittedApplication, status: "REJECTED" })]);
    await screen.findByRole("article", { name: "MED-2026-000123" });
    expect(screen.getByRole("button", { name: "تقديم طلب جديد" })).toBeEnabled();
  });

  it("creates the draft and opens it", async () => {
    const created = apiApplication({ id: "0d9b6c1e-1111-4000-8000-00000000abcd" });
    server.use(
      http.post(`${API}/applications/`, () => HttpResponse.json(created, { status: 201 })),
    );
    const { router, user } = setup([]);
    await user.click(await screen.findByRole("button", { name: "تقديم طلب جديد" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/application/${created.id}`),
    );
  });

  it("explains a loading failure and offers a retry", async () => {
    server.use(
      handlers.me(meDoctor),
      handlers.referenceData(),
      http.get(`${API}/applications/`, () =>
        HttpResponse.json({ error: { code: "SERVER_ERROR", message: "حدث خطأ في الخادم", fields: {} } }, { status: 500 }),
      ),
    );
    renderApp("/dashboard");
    expect(await screen.findByRole("alert")).toHaveTextContent("حدث خطأ في الخادم");
    expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeInTheDocument();
  });
});
