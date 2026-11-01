import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import {
  ADMIN_APP_ID,
  API,
  adminHandlers,
  apiAdminDetail,
  apiAdminDuesReceipt,
  apiAdminDuesRequest,
  DUES_ID,
  handlers,
  meAdmin,
  type ApiAdminDetail,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const underReview = apiAdminDetail({
  status: "UNDER_REVIEW",
  payment_status: "CONFIRMED",
  allowed_transitions: ["APPROVED", "NEEDS_CORRECTION", "REJECTED"],
});
const duesBase = `${API}/admin/applications/${ADMIN_APP_ID}/dues-requests/`;
const reviewable = (receiptId = "r-9") =>
  apiAdminDuesRequest({
    status: "PENDING_REVIEW",
    receipts: [apiAdminDuesReceipt({ id: receiptId })],
    allowed_actions: ["CONFIRM_RECEIPT", "REJECT_RECEIPT", "CANCEL"],
  });

function serve(detail: ApiAdminDetail, extra: Parameters<typeof server.use> = []) {
  server.use(
    ...extra,
    handlers.me(meAdmin),
    handlers.referenceData(),
    adminHandlers.notes(),
    adminHandlers.audit(),
    adminHandlers.detail(detail),
  );
}

async function open() {
  const view = renderApp(`/admin/applications/${ADMIN_APP_ID}`);
  await screen.findByRole("heading", { level: 1, name: /MED-2026-000001/ });
  return view;
}

const duesSection = () => screen.getByRole("region", { name: "المستحقات النقابية" });

describe("Admin: additional syndicate dues", () => {
  it("requests dues with an amount in Arabic digits and a reason, without changing the status", async () => {
    let body: unknown = null;
    const requested = apiAdminDuesRequest({ amount: "250.00", reason: "اشتراك 2026" });
    serve(underReview, [
      http.post(duesBase, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          {
            ...underReview,
            dues_requests: [requested],
            outstanding_dues_count: 1,
            allowed_transitions: ["NEEDS_CORRECTION", "REJECTED"],
          },
          { status: 201 },
        );
      }),
    ]);
    const { user } = await open();
    expect(within(duesSection()).getByText("لا توجد مستحقات نقابية مطلوبة لهذا الطلب.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "طلب سداد مستحقات نقابية" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "إرسال الطلب" }));
    expect(within(dialog).getByText("يرجى إدخال مبلغ صحيح أكبر من صفر (بحد أقصى رقمان عشريان).")).toBeInTheDocument();
    expect(body).toBeNull();

    await user.type(within(dialog).getByLabelText("المبلغ المطلوب (ج.م)"), "٢٥٠");
    await user.click(within(dialog).getByRole("button", { name: "إرسال الطلب" }));
    expect(within(dialog).getByText("يرجى كتابة سبب المستحقات وتفاصيلها.")).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("سبب المستحقات وتفاصيلها"), "اشتراك 2026");
    await user.click(within(dialog).getByRole("button", { name: "إرسال الطلب" }));
    await waitFor(() => expect(body).toEqual({ amount: "250", reason: "اشتراك 2026" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    expect(screen.getByRole("status")).toHaveTextContent("تم إرسال طلب سداد المستحقات للعضو.");
    expect(within(duesSection()).getByText("250 ج.م")).toBeInTheDocument();
    expect(within(duesSection()).getByText("اشتراك 2026")).toBeInTheDocument();
    expect(within(duesSection()).getByText("بانتظار السداد")).toBeInTheDocument();
    expect(screen.getByText("لا يمكن قبول الطلب قبل تأكيد سداد المستحقات النقابية المطلوبة (1).")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "قبول الطلب" })).not.toBeInTheDocument();
  });

  it("shows the server's field error in the dialog", async () => {
    serve(underReview, [
      http.post(duesBase, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "يرجى تصحيح الأخطاء المشار إليها",
              fields: { amount: ["يرجى إدخال مبلغ أكبر من صفر بالجنيه"] },
            },
          },
          { status: 400 },
        ),
      ),
    ]);
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "طلب سداد مستحقات نقابية" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("المبلغ المطلوب (ج.م)"), "5");
    await user.type(within(dialog).getByLabelText("سبب المستحقات وتفاصيلها"), "اشتراك");
    await user.click(within(dialog).getByRole("button", { name: "إرسال الطلب" }));
    expect(await within(dialog).findByText("يرجى إدخال مبلغ أكبر من صفر بالجنيه")).toBeInTheDocument();
  });

  it("lists every request with its receipts and review history", async () => {
    const rejected = apiAdminDuesReceipt({
      id: "r-1",
      status: "REJECTED",
      rejection_reason: "الإيصال غير واضح",
      reviewed_at: "2026-11-01T11:00:00+02:00",
      reviewed_by_email: "reviewer@dev.local",
    });
    const pending = apiAdminDuesReceipt({ id: "r-2", created_at: "2026-11-02T10:00:00+02:00" });
    const cancelled = apiAdminDuesRequest({
      id: "7d0e0c4a-0000-4000-8000-0000000000d2",
      amount: "100.00",
      reason: "رسوم قديمة",
      status: "CANCELLED",
      cancellation_reason: "مكرر",
      resolved_by_email: "reviewer@dev.local",
      resolved_at: "2026-11-01T12:00:00+02:00",
      allowed_actions: [],
    });
    serve({
      ...underReview,
      outstanding_dues_count: 1,
      dues_requests: [
        apiAdminDuesRequest({
          status: "PENDING_REVIEW",
          receipts: [rejected, pending],
          allowed_actions: ["CONFIRM_RECEIPT", "REJECT_RECEIPT", "CANCEL"],
        }),
        cancelled,
      ],
    });
    await open();
    const [first, closed] = within(duesSection()).getAllByRole("article");
    expect(within(first!).getByText("1٬250.50 ج.م")).toBeInTheDocument();
    expect(within(first!).getByText("الإيصال قيد المراجعة")).toBeInTheDocument();
    const receipts = within(first!).getAllByRole("listitem");
    expect(receipts).toHaveLength(2);
    expect(within(receipts[0]!).getByText("مرفوض")).toBeInTheDocument();
    expect(within(receipts[0]!).getByText("سبب الرفض: الإيصال غير واضح")).toBeInTheDocument();
    expect(within(receipts[0]!).getByText(/reviewer@dev\.local/)).toBeInTheDocument();
    expect(within(receipts[1]!).getByText("قيد المراجعة")).toBeInTheDocument();
    expect(within(first!).getByRole("button", { name: "تأكيد السداد" })).toBeInTheDocument();
    expect(within(first!).getByRole("button", { name: "رفض الإيصال" })).toBeInTheDocument();
    expect(within(first!).getByRole("button", { name: "إلغاء المطالبة" })).toBeInTheDocument();

    expect(within(closed!).getByText("ملغي")).toBeInTheDocument();
    expect(within(closed!).getByText("سبب الإلغاء: مكرر")).toBeInTheDocument();
    expect(within(closed!).queryByRole("button", { name: /تأكيد|رفض|إلغاء/ })).not.toBeInTheDocument();
  });

  it("opens a receipt in the document viewer", async () => {
    serve({ ...underReview, dues_requests: [reviewable()] });
    const { user } = await open();
    await user.click(within(duesSection()).getByRole("button", { name: /عرض الإيصال/ }));
    expect(await screen.findByRole("dialog", { name: /إيصال سداد مستحقات نقابية/ })).toBeInTheDocument();
  });

  it("rejects a receipt only with a reason, sending the receipt id", async () => {
    let body: unknown = null;
    serve({ ...underReview, dues_requests: [reviewable()] }, [
      http.post(`${duesBase}${DUES_ID}/review/`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(underReview);
      }),
    ]);
    const { user } = await open();
    await user.click(within(duesSection()).getByRole("button", { name: "رفض الإيصال" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "رفض الإيصال" }));
    expect(within(dialog).getByText("يرجى كتابة سبب الرفض.")).toBeInTheDocument();
    expect(body).toBeNull();
    await user.type(within(dialog).getByLabelText("سبب الرفض (يظهر للعضو)"), "المبلغ غير مطابق");
    await user.click(within(dialog).getByRole("button", { name: "رفض الإيصال" }));
    await waitFor(() => expect(body).toEqual({ receipt_id: "r-9", decision: "REJECTED", reason: "المبلغ غير مطابق" }));
    expect(await screen.findByRole("status")).toHaveTextContent("تم رفض الإيصال وإبلاغ العضو بالسبب.");
  });

  it("confirms a receipt", async () => {
    const confirm = vi.fn();
    serve({ ...underReview, dues_requests: [reviewable()] }, [
      http.post(`${duesBase}${DUES_ID}/review/`, async ({ request }) => {
        confirm(await request.json());
        return HttpResponse.json(underReview);
      }),
    ]);
    const { user } = await open();
    await user.click(within(duesSection()).getByRole("button", { name: "تأكيد السداد" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/1٬250\.50 ج\.م/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "تأكيد السداد" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith({ receipt_id: "r-9", decision: "CONFIRMED", reason: "" }));
    expect(await screen.findByRole("status")).toHaveTextContent("تم تأكيد سداد المستحقات.");
  });

  it("cancels an unresolved request with a recorded reason", async () => {
    let body: unknown = null;
    serve({ ...underReview, dues_requests: [apiAdminDuesRequest()] }, [
      http.post(`${duesBase}${DUES_ID}/cancel/`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(underReview);
      }),
    ]);
    const { user } = await open();
    await user.click(within(duesSection()).getByRole("button", { name: "إلغاء المطالبة" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("سبب الإلغاء (يُسجَّل ولا يظهر للعضو)"), "سُدد مباشرة");
    await user.click(within(dialog).getByRole("button", { name: "إلغاء المطالبة" }));
    await waitFor(() => expect(body).toEqual({ reason: "سُدد مباشرة" }));
  });

  it("offers no dues request when the server says it is not allowed", async () => {
    serve(
      apiAdminDetail({ status: "APPROVED", payment_status: "CONFIRMED", allowed_transitions: [], can_request_dues: false }),
    );
    await open();
    expect(screen.queryByRole("button", { name: "طلب سداد مستحقات نقابية" })).not.toBeInTheDocument();
  });
});
