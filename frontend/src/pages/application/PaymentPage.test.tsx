import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import {
  API,
  APP_ID,
  apiApplication,
  apiDocument,
  draftHandlers,
  handlers,
  meDoctor,
  type ApiApplication,
} from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const imageSize = vi.hoisted(() => ({ value: { width: 1200, height: 900 } as { width: number; height: number } | null }));
vi.mock("@/features/documents/imageSize", () => ({ readImageSize: () => Promise.resolve(imageSize.value) }));

const receipt = apiDocument({
  id: "d-r",
  document_type: "PAYMENT_RECEIPT",
  original_filename: "receipt.jpg",
  content_type: "image/jpeg",
  file_size: 1_572_864,
});

function serve(app: ApiApplication) {
  server.use(
    handlers.me(meDoctor),
    handlers.referenceData(),
    draftHandlers.application(app),
    draftHandlers.fees(app.id),
    draftHandlers.validation(app.id),
  );
}

async function openPayment(app: ApiApplication = apiApplication()) {
  serve(app);
  const view = renderApp(`/application/${APP_ID}/payment`);
  await screen.findByRole("heading", { name: "إيصال الدفع" });
  return view;
}

describe("PaymentPage (PROMPT.md §18)", () => {
  it("shows the fee summary with a banana header, instructions and the drop zone", async () => {
    await openPayment();
    expect(screen.getByRole("link", { name: "رجوع للاستمارة" })).toHaveAttribute("href", `/application/${APP_ID}/form`);
    const fees = await screen.findByRole("region", { name: "ملخص الرسوم" });
    expect(await within(fees).findByText("3٬025 ج.م")).toBeInTheDocument();
    expect(screen.getByText("اسحب صورة الإيصال هنا")).toBeInTheDocument();
    expect(screen.getByText("أو اضغط للاختيار")).toBeInTheDocument();
    expect(screen.getByText("JPG, PNG, WEBP — حتى 8 ميجابايت، وبحد أدنى 400×300 بكسل")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "متابعة للمراجعة" })).toBeDisabled();
  });

  it("rejects a 5×5 image before uploading", async () => {
    imageSize.value = { width: 5, height: 5 };
    const upload = vi.fn();
    server.use(
      http.post(`${API}/applications/${APP_ID}/documents/`, () => {
        upload();
        return HttpResponse.json(receipt, { status: 201 });
      }),
    );
    const { user } = await openPayment();
    await user.upload(screen.getByLabelText("إيصال الدفع"), new File(["x"], "tiny.png", { type: "image/png" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("أبعاد الصورة أقل من الحد الأدنى (400×300 بكسل).");
    expect(upload).not.toHaveBeenCalled();
    imageSize.value = { width: 1200, height: 900 };
  });

  it("uploads the receipt as PAYMENT_RECEIPT and then allows continuing to the review", async () => {
    let form: FormData | null = null;
    let app = apiApplication();
    server.use(
      http.post(`${API}/applications/${APP_ID}/documents/`, async ({ request }) => {
        form = await request.formData();
        app = apiApplication({ payment_status: "PENDING_REVIEW", documents: [receipt] });
        return HttpResponse.json(receipt, { status: 201 });
      }),
    );
    const { user, router } = await openPayment();
    server.use(http.get(`${API}/applications/${APP_ID}/`, () => HttpResponse.json(app)));
    await user.upload(screen.getByLabelText("إيصال الدفع"), new File(["x"], "receipt.jpg", { type: "image/jpeg" }));
    expect(await screen.findByText("receipt.jpg")).toBeInTheDocument();
    expect(form!.get("document_type")).toBe("PAYMENT_RECEIPT");
    expect(screen.getByText("حالة الدفع: بانتظار التأكيد")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "متابعة للمراجعة" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/review`));
  });

  it("shows the uploaded file bar with name, size and a remove action", async () => {
    let deleted = false;
    server.use(
      http.delete(`${API}/documents/d-r/`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = await openPayment(apiApplication({ payment_status: "PENDING_REVIEW", documents: [receipt] }));
    const bar = screen.getByRole("group", { name: "الإيصال المرفوع" });
    expect(bar).toHaveTextContent("receipt.jpg");
    expect(bar).toHaveTextContent("1.5 ميجابايت");
    server.use(draftHandlers.application(apiApplication()));
    await user.click(within(bar).getByRole("button", { name: "إزالة" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("اسحب صورة الإيصال هنا")).toBeInTheDocument();
  });
});

describe("PaymentPage when not editable", () => {
  it("redirects to the status page", async () => {
    serve(apiApplication({ status: "SUBMITTED", is_editable: false, reference_number: "MED-2026-000001" }));
    server.use(http.get(`${API}/applications/`, () => HttpResponse.json({ count: 0, results: [] })));
    const { router } = renderApp(`/application/${APP_ID}/payment`);
    await waitFor(() => expect(router.state.location.pathname).toBe(`/application/${APP_ID}/status`));
  });
});
