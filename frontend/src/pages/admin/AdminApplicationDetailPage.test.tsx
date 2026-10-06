import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import {
  ADMIN_APP_ID,
  API,
  adminHandlers,
  apiAdminDetail,
  handlers,
  meAdmin,
  page,
  type ApiAdminDetail,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const base = apiAdminDetail();
const detailPath = `/admin/applications/${ADMIN_APP_ID}`;

function serve(detail: ApiAdminDetail = base, extra: Parameters<typeof server.use> = []) {
  // Overrides first: MSW answers with the first matching handler.
  server.use(
    ...extra,
    handlers.me(meAdmin),
    handlers.referenceData(),
    adminHandlers.notes(),
    adminHandlers.audit(),
    adminHandlers.detail(detail),
  );
}

async function open(path = detailPath) {
  const view = renderApp(path);
  await screen.findByRole("heading", { level: 1, name: /MED-2026-000001/ });
  return view;
}

describe("AdminApplicationDetailPage (PROMPT.md §44)", () => {
  it("shows the member data with the national ID masked", async () => {
    serve();
    await open();
    const member = screen.getByRole("region", { name: "بيانات العضو" });
    expect(within(member).getByText("أحمد محمد علي حسن")).toBeInTheDocument();
    expect(within(member).getByText("28•••••••••234")).toBeInTheDocument();
    expect(within(member).getByText("01012345678")).toBeInTheDocument();
    expect(within(member).getByText("بشري")).toBeInTheDocument();
    expect(screen.getAllByText("مقدم").length).toBeGreaterThan(0);
    expect(screen.getAllByText("بانتظار التأكيد").length).toBeGreaterThan(0);
  });

  it("reveals the full national ID through the audited endpoint", async () => {
    const reveals: (string | null)[] = [];
    serve(base, [
      http.get(`${API}/admin/applications/${ADMIN_APP_ID}/`, ({ request }) => {
        const reveal = new URL(request.url).searchParams.get("reveal_national_id");
        reveals.push(reveal);
        return HttpResponse.json(
          reveal === "1"
            ? {
                ...base,
                doctor: { ...base.doctor, national_id: "28506150101234" },
                beneficiaries: base.beneficiaries.map((b) => ({ ...b, national_id: b.national_id ?? "28803150101242" })),
              }
            : base,
        );
      }),
    ]);
    const { user } = await open();
    expect(screen.getByText("يُسجَّل إظهار الرقم القومي في سجل المراجعة.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "إظهار الرقم القومي كاملاً" }));
    expect(await screen.findByText("28506150101234")).toBeInTheDocument();
    expect(reveals).toContain("1");
    expect(screen.getAllByText("28803150101242").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "إخفاء الرقم القومي" }));
    expect(await screen.findByText("28•••••••••234")).toBeInTheDocument();
    expect(screen.queryByText("28506150101234")).not.toBeInTheDocument();
  });

  it("lists the beneficiaries with their documents and opens a document in the viewer", async () => {
    serve();
    const { user } = await open();
    const table = screen.getByRole("table", { name: "المستفيدون" });
    const wife = within(table).getByRole("row", { name: /سارة محمود علي/ });
    expect(within(wife).getByText("زوجة")).toBeInTheDocument();
    expect(within(wife).getByText("1988")).toBeInTheDocument();

    await user.click(within(wife).getByRole("button", { name: "عرض شهادة الزواج" }));
    const dialog = await screen.findByRole("dialog", { name: "شهادة الزواج" });
    const image = within(dialog).getByRole("img", { name: "صورة المستند: شهادة الزواج" });
    const marriage = base.documents.find((d) => d.document_type === "MARRIAGE_CERTIFICATE");
    expect(image).toHaveAttribute("src", marriage?.content_url);
    expect(within(dialog).getByRole("link", { name: "فتح في نافذة جديدة" })).toHaveAttribute("target", "_blank");
  });

  it("marks a required beneficiary document that is missing", async () => {
    const [wife, ...rest] = base.beneficiaries;
    serve({ ...base, beneficiaries: [{ ...wife!, documents: [] }, ...rest] });
    await open();
    const row = within(screen.getByRole("table", { name: "المستفيدون" })).getByRole("row", { name: /سارة محمود علي/ });
    expect(within(row).getByText("شهادة الزواج: غير مرفق")).toBeInTheDocument();
  });

  it("shows the fee snapshot, never a recomputed quote", async () => {
    serve();
    await open();
    const fees = screen.getByRole("region", { name: "الرسوم المحسوبة عند التقديم" });
    expect(within(fees).getByText("2٬475 ج.م")).toBeInTheDocument();
    expect(within(fees).getByText("الدرجة 3")).toBeInTheDocument();
  });

  it("shows duplicate warnings", async () => {
    serve({ ...base, beneficiary_warnings: ["المستفيد سارة محمود علي: الرقم القومي مسجل كمستفيد في طلب آخر"] });
    await open();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("تنبيهات تكرار");
    expect(alert).toHaveTextContent("الرقم القومي مسجل كمستفيد في طلب آخر");
  });

  it("confirms the payment and shows the updated status", async () => {
    let body: unknown;
    serve(base, [
      http.post(`${API}/admin/applications/${ADMIN_APP_ID}/payment/`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...base, payment_status: "CONFIRMED" });
      }),
    ]);
    const { user } = await open();
    const payment = screen.getByRole("region", { name: "إيصال الدفع" });
    await user.click(within(payment).getByRole("button", { name: "تأكيد الدفع" }));
    const dialog = await screen.findByRole("dialog", { name: "تأكيد الدفع" });
    expect(dialog).toHaveTextContent("2٬475 ج.م");
    await user.type(within(dialog).getByRole("textbox"), "مطابق لكشف البنك");
    await user.click(within(dialog).getByRole("button", { name: "تأكيد" }));

    await waitFor(() => expect(body).toEqual({ payment_status: "CONFIRMED", note: "مطابق لكشف البنك" }));
    expect(await screen.findByText("تم تحديث حالة الدفع إلى: مؤكد")).toBeInTheDocument();
    expect(within(payment).queryByRole("button", { name: "تأكيد الدفع" })).not.toBeInTheDocument();
    expect(within(payment).getByRole("button", { name: "رفض الإيصال" })).toBeInTheDocument();
  });

  it("opens the receipt in the viewer", async () => {
    serve();
    const { user } = await open();
    const payment = screen.getByRole("region", { name: "إيصال الدفع" });
    await user.click(within(payment).getByRole("button", { name: "عرض الإيصال" }));
    expect(await screen.findByRole("dialog", { name: "إيصال الدفع" })).toBeInTheDocument();
  });

  it("offers only the server's allowed transitions", async () => {
    serve();
    await open();
    const actions = screen.getByRole("region", { name: "إجراءات المراجعة" });
    const labels = within(actions).getAllByRole("button").map((b) => b.textContent?.trim());
    expect(labels).toEqual(["بدء المراجعة", "طلب تصحيح", "رفض الطلب"]);
  });

  it("requires review notes for a correction and sends them", async () => {
    let body: unknown;
    serve(base, [
      http.post(`${API}/admin/applications/${ADMIN_APP_ID}/transition/`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          ...base,
          status: "NEEDS_CORRECTION",
          review_notes: "صورة البطاقة غير واضحة",
          allowed_transitions: [],
        });
      }),
    ]);
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "طلب تصحيح" }));
    const dialog = await screen.findByRole("dialog", { name: /طلب تصحيح/ });
    expect(dialog).toHaveTextContent("تظهر هذه الملاحظات للعضو");

    await user.click(within(dialog).getByRole("button", { name: "تأكيد" }));
    expect(within(dialog).getByText("يرجى كتابة ملاحظات المراجعة")).toBeInTheDocument();
    expect(body).toBeUndefined();

    await user.type(within(dialog).getByRole("textbox", { name: /ملاحظات المراجعة/ }), "صورة البطاقة غير واضحة");
    await user.click(within(dialog).getByRole("button", { name: "تأكيد" }));
    await waitFor(() => expect(body).toEqual({ to_status: "NEEDS_CORRECTION", review_notes: "صورة البطاقة غير واضحة" }));
    expect(await screen.findByText("تم تحديث حالة الطلب إلى: يحتاج تصحيح")).toBeInTheDocument();
    const notes = screen.getByRole("region", { name: "ملاحظات المراجعة (تظهر للعضو)" });
    expect(within(notes).getByText("صورة البطاقة غير واضحة")).toBeInTheDocument();
  });

  it("shows the server's refusal inside the dialog", async () => {
    serve({ ...base, status: "UNDER_REVIEW", payment_status: "CONFIRMED", allowed_transitions: ["APPROVED", "NEEDS_CORRECTION", "REJECTED"] }, [
      http.post(`${API}/admin/applications/${ADMIN_APP_ID}/transition/`, () =>
        HttpResponse.json(
          { error: { code: "INVALID_STATUS_TRANSITION", message: "لا يمكن قبول الطلب قبل تأكيد الدفع", fields: {} } },
          { status: 409 },
        ),
      ),
    ]);
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "قبول الطلب" }));
    const dialog = await screen.findByRole("dialog", { name: /قبول الطلب/ });
    await user.click(within(dialog).getByRole("button", { name: "تأكيد" }));
    expect(await within(dialog).findByText("لا يمكن قبول الطلب قبل تأكيد الدفع")).toBeInTheDocument();
  });

  it("explains why approval is not offered before the payment is confirmed", async () => {
    serve({ ...base, status: "UNDER_REVIEW", allowed_transitions: ["NEEDS_CORRECTION", "REJECTED"] });
    await open();
    expect(screen.getByText("يجب تأكيد الدفع قبل قبول الطلب.")).toBeInTheDocument();
  });

  it("adds an internal note and lists it", async () => {
    let notes: { id: string; body: string; author_email: string; created_at: string }[] = [];
    serve(base, [
      http.get(`${API}/admin/applications/${ADMIN_APP_ID}/notes/`, () => HttpResponse.json(notes)),
      http.post(`${API}/admin/applications/${ADMIN_APP_ID}/notes/`, async ({ request }) => {
        const { body } = (await request.json()) as { body: string };
        const note = { id: "n1", body, author_email: "admin@dev.local", created_at: "2026-10-06T10:00:00+03:00" };
        notes = [note];
        return HttpResponse.json(note, { status: 201 });
      }),
    ]);
    const { user } = await open();
    const panel = screen.getByRole("region", { name: "ملاحظات داخلية" });
    expect(await within(panel).findByText("لا توجد ملاحظات داخلية.")).toBeInTheDocument();
    await user.type(within(panel).getByRole("textbox", { name: "ملاحظة جديدة" }), "اتصلت بالعضو هاتفياً");
    await user.click(within(panel).getByRole("button", { name: "إضافة ملاحظة" }));
    expect(await within(panel).findByText("اتصلت بالعضو هاتفياً")).toBeInTheDocument();
    expect(within(panel).getByRole("textbox", { name: "ملاحظة جديدة" })).toHaveValue("");
  });

  it("shows the audit history with Arabic action names", async () => {
    serve(base, [
      adminHandlers.audit(ADMIN_APP_ID, {
        ...page([
          {
            id: "e1",
            action: "APPLICATION_STATUS_CHANGED",
            timestamp: "2026-10-04T12:00:00+03:00",
            user_id: "u1",
            user_email: "admin@dev.local",
            object_type: "applications.insuranceapplication",
            object_id: ADMIN_APP_ID,
            metadata: { from: "SUBMITTED", to: "UNDER_REVIEW", notes: false },
          },
          {
            id: "e2",
            action: "APPLICATION_SUBMITTED",
            timestamp: "2026-10-03T09:15:00+03:00",
            user_id: "u2",
            user_email: "doctor@dev.local",
            object_type: "applications.insuranceapplication",
            object_id: ADMIN_APP_ID,
            metadata: {},
          },
        ]),
      }),
    ]);
    await open();
    const audit = screen.getByRole("region", { name: "سجل المراجعة" });
    const items = await within(audit).findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("تغيير حالة الطلب");
    expect(items[0]).toHaveTextContent("مقدم ← قيد المراجعة");
    expect(items[0]).toHaveTextContent("admin@dev.local");
    expect(items[1]).toHaveTextContent("تقديم الطلب");
  });

  it("links to the admin print view", async () => {
    serve();
    await open();
    expect(screen.getByRole("link", { name: "طباعة الاستمارة" })).toHaveAttribute("href", `${detailPath}/print`);
  });
});
