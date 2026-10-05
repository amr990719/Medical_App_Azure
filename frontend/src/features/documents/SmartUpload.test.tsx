import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { toCamel } from "@/api/case";
import type { DocumentSummary } from "@/api/types";
import { API } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { SmartUpload } from "./SmartUpload";

const LABEL = "صورة البطاقة (وجه)";

const uploaded = {
  id: "d1",
  document_type: "NATIONAL_ID_FRONT",
  beneficiary_id: null,
  original_filename: "front.png",
  content_type: "image/png",
  file_size: 2048,
  scan_status: "SKIPPED",
  created_at: "2026-10-05T10:00:00+03:00",
  content_url: "/api/v1/documents/d1/content/",
} as const;

const png = (name = "front.png", size?: number) => {
  const file = new File(["png-bytes"], name, { type: "image/png" });
  if (size) Object.defineProperty(file, "size", { value: size });
  return file;
};

function renderUpload(props: Partial<Parameters<typeof SmartUpload>[0]> = {}) {
  const onUploaded = vi.fn();
  const view = renderWithProviders(
    <SmartUpload
      applicationId="a1"
      documentType="NATIONAL_ID_FRONT"
      label={LABEL}
      required
      document={null}
      onUploaded={onUploaded}
      {...props}
    />,
  );
  return { ...view, onUploaded, input: screen.getByLabelText(LABEL) as HTMLInputElement };
}

describe("SmartUpload", () => {
  it("accepts only the content types allowed by reference data", () => {
    const { input } = renderUpload();
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
  });

  it("uploads immediately on select and confirms the attachment", async () => {
    let form: FormData | null = null;
    server.use(
      http.post(`${API}/applications/a1/documents/`, async ({ request }) => {
        form = await request.formData();
        return HttpResponse.json(uploaded, { status: 201 });
      }),
    );
    const { user, input, onUploaded } = renderUpload({ beneficiaryId: "b1" });
    await user.upload(input, png());
    expect(await screen.findByText("✓ تم الإرفاق: front.png")).toBeInTheDocument();
    expect(form!.get("document_type")).toBe("NATIONAL_ID_FRONT");
    expect(form!.get("beneficiary_id")).toBe("b1");
    // jsdom's XHR -> MSW bridge drops the multipart filename (browsers keep it); check the bytes.
    const part = form!.get("file") as File;
    expect(part.type).toBe("image/png");
    expect(await part.text()).toBe("png-bytes");
    expect(onUploaded).toHaveBeenCalledWith(toCamel(uploaded));
  });

  it("shows progress while uploading", async () => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.post(`${API}/applications/a1/documents/`, async () => {
        await held; // the response waits until the test has seen the progress bar
        return HttpResponse.json(uploaded, { status: 201 });
      }),
    );
    const { user, input } = renderUpload();
    await user.upload(input, png());
    expect(await screen.findByRole("progressbar", { name: LABEL })).toBeInTheDocument();
    release();
    await screen.findByText("✓ تم الإرفاق: front.png");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("refuses a file larger than the limit before uploading", async () => {
    const { user, input, onUploaded } = renderUpload();
    await user.upload(input, png("big.png", 9 * 1024 * 1024));
    expect(await screen.findByRole("alert")).toHaveTextContent("حجم الملف أكبر من الحد المسموح (8 ميجابايت).");
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("refuses an unsupported type before uploading", async () => {
    const { input, onUploaded } = renderUpload();
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(input, new File(["MZ"], "setup.exe", { type: "application/x-msdownload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("نوع الملف غير مدعوم");
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("shows the server's Arabic message when the upload is refused", async () => {
    server.use(
      http.post(`${API}/applications/a1/documents/`, () =>
        HttpResponse.json(
          { error: { code: "IMAGE_TOO_SMALL", message: "أبعاد الصورة أصغر من المطلوب", fields: {} } },
          { status: 400 },
        ),
      ),
    );
    const { user, input, onUploaded } = renderUpload();
    await user.upload(input, png());
    expect(await screen.findByRole("alert")).toHaveTextContent("أبعاد الصورة أصغر من المطلوب");
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("shows an existing document with a replace action and its thumbnail", () => {
    renderUpload({ document: toCamel(uploaded) as DocumentSummary });
    expect(screen.getByText("✓ تم الإرفاق: front.png")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /استبدال/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "معاينة front.png" })).toHaveAttribute(
      "src",
      "/api/v1/documents/d1/content/",
    );
  });

  it("marks required slots", () => {
    renderUpload();
    expect(screen.getByText("مطلوب")).toBeInTheDocument();
  });

  it("is read-only when disabled", () => {
    const { input } = renderUpload({ disabled: true });
    expect(input).toBeDisabled();
  });

  it("clears the error after a successful retry", async () => {
    server.use(
      http.post(`${API}/applications/a1/documents/`, () => HttpResponse.json(uploaded, { status: 201 })),
    );
    const { user, input } = renderUpload();
    await user.upload(input, png("big.png", 9 * 1024 * 1024));
    await screen.findByRole("alert");
    await user.upload(input, png());
    await screen.findByText("✓ تم الإرفاق: front.png");
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});
