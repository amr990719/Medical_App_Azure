import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import {
  API,
  APP_ID,
  apiApplication,
  apiDuesReceipt,
  apiDuesRequest,
  DUES_ID,
  handlers,
  meDoctor,
  type ApiApplication,
  type ApiDuesRequest,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const imageSize = vi.hoisted(() => ({ value: { width: 1200, height: 900 } as { width: number; height: number } | null }));
vi.mock("@/features/documents/imageSize", () => ({ readImageSize: () => Promise.resolve(imageSize.value) }));

const underReview = (dues: ApiDuesRequest[]) =>
  apiApplication({
    status: "UNDER_REVIEW",
    is_editable: false,
    payment_status: "CONFIRMED",
    reference_number: "MED-2026-000123",
    submitted_at: "2026-10-03T09:15:00+03:00",
    fee_snapshot: { total: 3025, tier: 3 },
    dues_requests: dues,
  });

const receiptUrl = `${API}/applications/${APP_ID}/dues-requests/${DUES_ID}/receipts/`;

function serve(app: () => ApiApplication, extra: Parameters<typeof server.use> = []) {
  server.use(
    ...extra,
    handlers.me(meDoctor),
    handlers.referenceData(),
    http.get(`${API}/applications/${APP_ID}/`, () => HttpResponse.json(app())),
  );
}

async function openStatus() {
  const view = renderApp(`/application/${APP_ID}/status`);
  await screen.findByText("MED-2026-000123");
  return view;
}

const outstanding = () => screen.getByRole("region", { name: "مستحقات نقابية مطلوبة" });

describe("StatusPage: additional syndicate dues", () => {
  it("shows an outstanding request prominently with the amount and the admin's explanation", async () => {
    serve(() => underReview([apiDuesRequest()]));
    await openStatus();
    const region = outstanding();
    expect(within(region).getByText("1٬250.50 ج.م")).toBeInTheDocument();
    expect(within(region).getByText("اشتراك النقابة الفرعية لعام 2026")).toBeInTheDocument();
    expect(
      within(region).getByText("يرجى سداد المبلغ ثم رفع صورة إيصال السداد. لا يمكن قبول طلبك قبل تأكيد السداد."),
    ).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "رفع إيصال السداد" })).toBeEnabled();
    // No edit or resubmission is offered for it.
    expect(screen.queryByRole("link", { name: "تصحيح وإعادة التقديم" })).not.toBeInTheDocument();
  });

  it("uploads a receipt for that request; it is then under review, not paid", async () => {
    let form: FormData | null = null;
    let dues = apiDuesRequest();
    serve(() => underReview([dues]), [
      http.post(receiptUrl, async ({ request }) => {
        form = await request.formData();
        dues = apiDuesRequest({ status: "PENDING_REVIEW", can_upload_receipt: false, receipts: [apiDuesReceipt()] });
        return HttpResponse.json(dues, { status: 201 });
      }),
    ]);
    const { user } = await openStatus();
    await user.upload(within(outstanding()).getByLabelText("رفع إيصال السداد"), new File(["x"], "dues.jpg", { type: "image/jpeg" }));
    await waitFor(() => expect(form?.has("file")).toBe(true));
    expect(await within(outstanding()).findByText("الإيصال قيد المراجعة")).toBeInTheDocument();
    expect(within(outstanding()).queryByRole("button", { name: "رفع إيصال السداد" })).not.toBeInTheDocument();
    expect(screen.queryByText("تم تأكيد السداد")).not.toBeInTheDocument();
  });

  it("checks the receipt dimensions before uploading", async () => {
    imageSize.value = { width: 10, height: 10 };
    const upload = vi.fn();
    serve(() => underReview([apiDuesRequest()]), [
      http.post(receiptUrl, () => {
        upload();
        return HttpResponse.json(apiDuesRequest(), { status: 201 });
      }),
    ]);
    const { user } = await openStatus();
    await user.upload(within(outstanding()).getByLabelText("رفع إيصال السداد"), new File(["x"], "tiny.png", { type: "image/png" }));
    expect(await within(outstanding()).findByRole("alert")).toHaveTextContent("أبعاد الصورة أقل من الحد الأدنى (400×300 بكسل).");
    expect(upload).not.toHaveBeenCalled();
    imageSize.value = { width: 1200, height: 900 };
  });

  it("after a rejection shows the reason, keeps the earlier submission and allows another upload", async () => {
    const rejected = apiDuesReceipt({
      status: "REJECTED",
      rejection_reason: "الإيصال غير واضح",
      reviewed_at: "2026-11-01T12:00:00+02:00",
    });
    serve(() => underReview([apiDuesRequest({ status: "REJECTED", receipts: [rejected] })]));
    await openStatus();
    const region = outstanding();
    expect(within(region).getByText("تم رفض الإيصال: الإيصال غير واضح")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "رفع إيصال السداد" })).toBeEnabled();
    const history = within(region).getByRole("list", { name: "الإيصالات المرفوعة" });
    expect(within(history).getByText("مرفوض")).toBeInTheDocument();
    expect(within(history).getByRole("link", { name: /عرض/ })).toHaveAttribute("href", "/api/v1/documents/doc-r-1/content/");
  });

  it("lists settled requests apart from the outstanding ones", async () => {
    serve(() =>
      underReview([
        apiDuesRequest({ status: "CONFIRMED", can_upload_receipt: false, amount: "300.00" }),
        apiDuesRequest({ id: "other", status: "CANCELLED", can_upload_receipt: false, amount: "75.00" }),
      ]),
    );
    await openStatus();
    expect(screen.queryByRole("region", { name: "مستحقات نقابية مطلوبة" })).not.toBeInTheDocument();
    const settled = screen.getByRole("region", { name: "مستحقات نقابية سابقة" });
    expect(within(settled).getByText("300 ج.م")).toBeInTheDocument();
    expect(within(settled).getByText("تم تأكيد السداد")).toBeInTheDocument();
    expect(within(settled).getByText("ملغي")).toBeInTheDocument();
  });

  it("shows nothing about dues when none were requested", async () => {
    serve(() => underReview([]));
    await openStatus();
    expect(screen.queryByRole("region", { name: "مستحقات نقابية مطلوبة" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "مستحقات نقابية سابقة" })).not.toBeInTheDocument();
  });
});
