import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { toCamel } from "@/api/case";
import type { DocumentSummary } from "@/api/types";
import { apiDocument } from "@/test/fixtures";
import { DocumentViewer } from "./DocumentViewer";

const summary = (contentType: string, filename: string) =>
  toCamel(apiDocument({ id: "d-1", content_type: contentType, original_filename: filename })) as DocumentSummary;

describe("DocumentViewer (PROMPT.md §44)", () => {
  it("shows an image inline from the authorized content endpoint", () => {
    render(<DocumentViewer document={summary("image/png", "front.png")} label="صورة البطاقة (وجه)" onClose={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("img", { name: "صورة المستند: صورة البطاقة (وجه)" })).toHaveAttribute(
      "src",
      "/api/v1/documents/d-1/content/",
    );
  });

  it.each([
    ["application/pdf", "شهادة.pdf"],
    ["image/heic", "photo.heic"],
  ])("never frames %s: it offers the download the server sends instead (Q-T17)", (type, filename) => {
    const { container } = render(
      <DocumentViewer document={summary(type, filename)} label="شهادة الميلاد" onClose={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(container.ownerDocument.querySelector("iframe, object, embed")).toBeNull();
    expect(within(dialog).queryByRole("img")).toBeNull();
    expect(within(dialog).getByText("لا يمكن عرض هذا الملف داخل الصفحة. قم بتنزيله لفتحه.")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "تنزيل الملف" })).toHaveAttribute(
      "href",
      "/api/v1/documents/d-1/content/",
    );
  });
});
