import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { toCamel } from "@/api/case";
import type { ReferenceData } from "@/api/types";
import type { components } from "@/api/schema";
import { ADMIN_APP_ID, API, apiReferenceData } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { NotificationsPanel } from "./NotificationsPanel";

type Row = components["schemas"]["NotificationHistory"];

const reference = toCamel(apiReferenceData) as ReferenceData;
const listUrl = `${API}/admin/applications/${ADMIN_APP_ID}/notifications/`;

function row(overrides: Partial<Row> = {}): Row {
  return {
    id: "n-1",
    event: "APPROVED",
    channel: "WHATSAPP",
    status: "DELIVERED",
    recipient_masked: "+20••••••789",
    error_code: "",
    attempts: 1,
    fallback_of: "",
    created_by_email: null,
    created_at: "2026-11-01T10:00:00+02:00",
    sent_at: null,
    delivered_at: null,
    ...overrides,
  } as Row;
}

function serve(rows: Row[]) {
  server.use(http.get(listUrl, () => HttpResponse.json(rows)));
}

async function show(rows: Row[]) {
  serve(rows);
  const view = renderWithProviders(<NotificationsPanel applicationId={ADMIN_APP_ID} reference={reference} />);
  await screen.findByRole("region", { name: "الإشعارات" });
  return view;
}

const item = (n = 0) => screen.getAllByRole("listitem")[n]!;

describe("NotificationsPanel", () => {
  it("shows event, channel, status, time, and the masked recipient in an LTR span", async () => {
    await show([row()]);
    const li = await waitFor(() => item());
    expect(within(li).getByText("قبول الطلب")).toBeInTheDocument();
    expect(within(li).getByText("واتساب")).toBeInTheDocument();
    expect(within(li).getByText("تم التسليم")).toBeInTheDocument();
    expect(within(li).getByText(/نوفمبر/)).toBeInTheDocument();
    const recipient = within(li).getByText("+20••••••789");
    expect(recipient).toHaveAttribute("dir", "ltr");
  });

  it("marks FAILED and EXPIRED rows prominently", async () => {
    await show([row({ id: "a", status: "FAILED" }), row({ id: "b", status: "EXPIRED" })]);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(item(0)).toHaveAttribute("data-notification-tone", "alert");
    expect(item(1)).toHaveAttribute("data-notification-tone", "alert");
  });

  it("shows SUPERSEDED quietly as no longer needed, without a resend button", async () => {
    await show([row({ status: "SUPERSEDED" })]);
    const li = await waitFor(() => item());
    expect(li).toHaveAttribute("data-notification-tone", "quiet");
    expect(within(li).getByText("لم يعد مطلوبًا")).toBeInTheDocument();
    expect(within(li).queryByRole("button", { name: "إعادة الإرسال" })).not.toBeInTheDocument();
  });

  it("labels a SENT email as accepted, delivery not confirmed, never delivered", async () => {
    await show([row({ channel: "EMAIL", status: "SENT" })]);
    const li = await waitFor(() => item());
    expect(within(li).getByText("قبله مزوّد البريد، والتسليم غير مؤكد")).toBeInTheDocument();
    expect(within(li).queryByText("تم التسليم")).not.toBeInTheDocument();
  });

  it("labels a SENT WhatsApp row as sent, awaiting delivery", async () => {
    await show([row({ channel: "WHATSAPP", status: "SENT" })]);
    const li = await waitFor(() => item());
    expect(within(li).getByText("أُرسل، بانتظار تأكيد التسليم")).toBeInTheDocument();
  });

  it("explains known error codes in Arabic and uses a generic line for unknown ones", async () => {
    await show([
      row({ id: "a", status: "EXPIRED", error_code: "NO_DELIVERY_RECEIPT" }),
      row({ id: "b", status: "FAILED", error_code: "131026" }),
    ]);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(within(item(0)).getByText("لم يصل تأكيد التسليم خلال المهلة، وحُوّل إلى البريد.")).toBeInTheDocument();
    expect(within(item(1)).getByText("رفض مزود الخدمة الرسالة (الرمز: 131026).")).toBeInTheDocument();
  });

  it("words WhatsApp lines as moved to email, never as sent", async () => {
    await show([
      row({ id: "a", status: "FAILED", error_code: "OPTED_OUT" }),
      row({ id: "b", status: "EXPIRED", error_code: "NO_DELIVERY_RECEIPT" }),
      row({ id: "c", status: "FAILED", error_code: "UNKNOWN_RESULT" }),
    ]);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(within(item(0)).getByText("لم يفعّل العضو رسائل واتساب، وحُوّل إلى البريد.")).toBeInTheDocument();
    expect(within(item(1)).getByText("لم يصل تأكيد التسليم خلال المهلة، وحُوّل إلى البريد.")).toBeInTheDocument();
    expect(within(item(2)).getByText("نتيجة الإرسال غير معروفة، وحُوّل إلى البريد.")).toBeInTheDocument();
    expect(screen.queryByText(/فأُرسل/)).not.toBeInTheDocument();
  });

  it("explains that WhatsApp is switched off and the message moved to email", async () => {
    await show([row({ id: "a", status: "FAILED", error_code: "WHATSAPP_DISABLED" })]);
    const li = await waitFor(() => item());
    expect(within(li).getByText("واتساب غير مفعّل حاليًا، فحُوّل إلى البريد.")).toBeInTheDocument();
  });

  it("never claims an email was sent when its result is unknown", async () => {
    await show([row({ channel: "EMAIL", status: "FAILED", error_code: "UNKNOWN_RESULT" })]);
    const li = await waitFor(() => item());
    expect(within(li).getByText("نتيجة الإرسال غير معروفة ولم يتأكد الإرسال.")).toBeInTheDocument();
    expect(within(li).queryByText(/حُوّل|فأُرسل/)).not.toBeInTheDocument();
  });

  it("never shows an error for a row that retried and then succeeded", async () => {
    await show([
      row({ id: "a", status: "DELIVERED", error_code: "CONNECT_FAILED", attempts: 2 }),
      row({ id: "b", channel: "EMAIL", status: "SENT", error_code: "SEND_ERROR", attempts: 3 }),
    ]);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(screen.queryByText("تعذر الاتصال بمزود الخدمة.")).not.toBeInTheDocument();
    expect(screen.queryByText("حدث خطأ أثناء الإرسال.")).not.toBeInTheDocument();
    expect(item(0)).not.toHaveAttribute("data-notification-tone", "alert");
    expect(item(1)).not.toHaveAttribute("data-notification-tone", "alert");
  });

  it("resends only after confirming in the dialog, and refreshes the list", async () => {
    let posts = 0;
    let rows = [row({ status: "FAILED", error_code: "SEND_ERROR" })];
    server.use(
      http.get(listUrl, () => HttpResponse.json(rows)),
      http.post(`${listUrl}n-1/resend/`, () => {
        posts += 1;
        const created = row({ id: "n-2", status: "PENDING", fallback_of: "" });
        rows = [created, ...rows];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    const { user } = renderWithProviders(<NotificationsPanel applicationId={ADMIN_APP_ID} reference={reference} />);
    await user.click(await screen.findByRole("button", { name: "إعادة الإرسال" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("سيُرسل هذا الإشعار إلى العضو مرة أخرى. هل تريد المتابعة؟")).toBeInTheDocument();
    expect(posts).toBe(0);
    await user.click(within(dialog).getByRole("button", { name: "إعادة الإرسال" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts).toBe(1);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(screen.getByRole("status")).toHaveTextContent("تمت إضافة الإشعار إلى قائمة الإرسال.");
  });

  it("shows the server message on a 409 and keeps the row list", async () => {
    server.use(
      http.get(listUrl, () => HttpResponse.json([row({ status: "FAILED" })])),
      http.post(`${listUrl}n-1/resend/`, () =>
        HttpResponse.json(
          { error: { code: "NOTIFICATION_CONFLICT", message: "هناك إشعار مماثل قيد الإرسال.", fields: {} } },
          { status: 409 },
        ),
      ),
    );
    const { user } = renderWithProviders(<NotificationsPanel applicationId={ADMIN_APP_ID} reference={reference} />);
    await user.click(await screen.findByRole("button", { name: "إعادة الإرسال" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "إعادة الإرسال" }));
    expect(await within(dialog).findByText("هناك إشعار مماثل قيد الإرسال.")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows the empty state when there are no rows", async () => {
    await show([]);
    expect(await screen.findByText("لا توجد إشعارات لهذا الطلب بعد.")).toBeInTheDocument();
  });
});
