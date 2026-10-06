import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API, APP_ID, apiApplication, handlers, meDoctor, type ApiApplication } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const submitted = apiApplication({
  status: "SUBMITTED",
  is_editable: false,
  payment_status: "PENDING_REVIEW",
  reference_number: "MED-2026-000123",
  submitted_at: "2026-10-03T09:15:00+03:00",
  fee_snapshot: { total: 3025, tier: 3 },
});

function serve(app: ApiApplication) {
  server.use(handlers.me(meDoctor), handlers.referenceData(), http.get(`${API}/applications/${APP_ID}/`, () => HttpResponse.json(app)));
}

async function openStatus() {
  const view = renderApp(`/application/${APP_ID}/status`);
  await screen.findByRole("heading", { name: "حالة الطلب" });
  return view;
}

const stepStates = () =>
  within(screen.getByRole("list", { name: "مراحل الطلب" }))
    .getAllByRole("listitem")
    .map((item) => item.getAttribute("data-state"));

afterEach(() => vi.useRealTimers());

describe("StatusPage (PROMPT.md §43)", () => {
  it("shows the reference number, status, submission date and amount", async () => {
    serve(submitted);
    await openStatus();
    expect(await screen.findByText("MED-2026-000123")).toBeInTheDocument();
    expect(screen.getByText("مقدم")).toBeInTheDocument();
    expect(screen.getByText(/٣ أكتوبر ٢٠٢٦/)).toBeInTheDocument();
    expect(screen.getByText("3٬025 ج.م")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "طباعة الاستمارة" })).toHaveAttribute("href", `/application/${APP_ID}/print`);
  });

  it("draws the timeline تم التقديم ✓ → قيد المراجعة → إشعار بالنتيجة", async () => {
    serve(submitted);
    await openStatus();
    await screen.findByText("MED-2026-000123");
    expect(stepStates()).toEqual(["complete", "current", "upcoming"]);
  });

  it("marks the result step with the decision and shows the review notes", async () => {
    serve({ ...submitted, status: "APPROVED", payment_status: "CONFIRMED", review_notes: "مرحباً بك في المشروع" });
    await openStatus();
    await screen.findByText("MED-2026-000123");
    expect(stepStates()).toEqual(["complete", "complete", "complete"]);
    expect(screen.getByText("تم قبول الطلب")).toBeInTheDocument();
    expect(screen.getByText("مرحباً بك في المشروع")).toBeInTheDocument();
  });

  it("offers correct-and-resubmit with the notes when a correction is needed", async () => {
    serve({ ...submitted, status: "NEEDS_CORRECTION", is_editable: true, review_notes: "صورة البطاقة غير واضحة" });
    await openStatus();
    expect(await screen.findByText("صورة البطاقة غير واضحة")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تصحيح وإعادة التقديم" })).toHaveAttribute("href", `/application/${APP_ID}/form`);
  });

  it("polls while the application waits for review and stops once decided", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let current: ApiApplication = submitted;
    let calls = 0;
    server.use(
      handlers.me(meDoctor),
      handlers.referenceData(),
      http.get(`${API}/applications/${APP_ID}/`, () => {
        calls += 1;
        return HttpResponse.json(current);
      }),
    );
    await openStatus();
    await screen.findByText("مقدم");
    current = { ...submitted, status: "UNDER_REVIEW" };
    await act(() => vi.advanceTimersByTimeAsync(45_000));
    await waitFor(() => expect(document.querySelector('[data-status="UNDER_REVIEW"]')).not.toBeNull());
    current = { ...submitted, status: "APPROVED", payment_status: "CONFIRMED" };
    await act(() => vi.advanceTimersByTimeAsync(45_000));
    await screen.findByText("تم قبول الطلب");
    const after = calls;
    await act(() => vi.advanceTimersByTimeAsync(120_000));
    expect(calls).toBe(after);
  });
});
