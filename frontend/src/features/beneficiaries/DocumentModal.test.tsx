import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { Beneficiary } from "@/api/types";
import { API } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { DocumentModal } from "./DocumentModal";

const wife: Beneficiary = {
  id: "b1",
  rowNumber: 1,
  kinship: "WIFE",
  fullName: "سارة محمود علي",
  birthYear: 1990,
  nationalId: "29001011234567",
  isActive: true,
  requiredDocuments: [
    { type: "BENEFICIARY_NATIONAL_ID", required: true, label: "بطاقة الرقم القومي", ocrCapable: true },
    { type: "MARRIAGE_CERTIFICATE", required: true, label: "شهادة الزواج", ocrCapable: false },
    { type: "INSURANCE_PRINT", required: false, label: "برينت تأميني", ocrCapable: false },
  ],
  documents: [
    {
      id: "d9",
      documentType: "MARRIAGE_CERTIFICATE",
      beneficiaryId: "b1",
      originalFilename: "marriage.jpg",
      contentType: "image/jpeg",
      fileSize: 1000,
      scanStatus: "SKIPPED",
      createdAt: "2026-10-05T10:00:00+03:00",
      contentUrl: "/api/v1/documents/d9/content/",
    },
  ],
  updatedAt: "2026-10-05T10:00:00+03:00",
};

function renderModal(beneficiary: Beneficiary = wife) {
  const onClose = vi.fn();
  const view = renderWithProviders(
    <DocumentModal open applicationId="a1" beneficiary={beneficiary} onClose={onClose} />,
  );
  return { ...view, onClose };
}

describe("DocumentModal", () => {
  it("is titled with the beneficiary name", () => {
    renderModal();
    expect(screen.getByRole("dialog", { name: "مستندات المستفيد: سارة محمود علي" })).toBeInTheDocument();
  });

  it("has one slot per document from the server rules, with required/optional marks", () => {
    renderModal();
    const dialog = screen.getByRole("dialog");
    const slots = within(dialog).getAllByRole("group");
    expect(slots.map((slot) => slot.querySelector("legend")?.textContent)).toEqual([
      "بطاقة الرقم القومي",
      "شهادة الزواج",
      "برينت تأميني",
    ]);
    expect(within(slots[0]!).getByText("مطلوب")).toBeInTheDocument();
    expect(within(slots[2]!).getByText("اختياري")).toBeInTheDocument();
  });

  it("shows documents that are already attached", () => {
    renderModal();
    const slot = screen.getByRole("group", { name: "شهادة الزواج" });
    expect(within(slot).getByText("✓ تم الإرفاق: marriage.jpg")).toBeInTheDocument();
  });

  it("closes with حفظ وإغلاق and with Escape", async () => {
    const { user, onClose } = renderModal();
    await user.click(screen.getByRole("button", { name: "حفظ وإغلاق" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("names an unnamed beneficiary", () => {
    renderModal({ ...wife, fullName: "" });
    expect(screen.getByRole("dialog", { name: "مستندات المستفيد: مستفيد بدون اسم" })).toBeInTheDocument();
  });

  it("offers مسح تلقائي only on OCR-capable slots and hands the suggestions back", async () => {
    server.use(
      http.post(`${API}/documents/d-nid/extract/`, () =>
        HttpResponse.json({ document_id: "d-nid", document_type: "BENEFICIARY_NATIONAL_ID", fields: { name: "سارة" } }),
      ),
    );
    const withId: Beneficiary = {
      ...wife,
      documents: [
        ...wife.documents,
        { ...wife.documents[0]!, id: "d-nid", documentType: "BENEFICIARY_NATIONAL_ID", contentUrl: "/x" },
      ],
    };
    const onExtracted = vi.fn();
    const { user } = renderWithProviders(
      <DocumentModal open applicationId="a1" beneficiary={withId} onClose={vi.fn()} onExtracted={onExtracted} />,
    );
    const scans = screen.getAllByRole("button", { name: "مسح تلقائي" });
    expect(scans).toHaveLength(1); // the marriage certificate is stored but not OCR-capable
    await user.click(scans[0]!);
    await waitFor(() => expect(onExtracted).toHaveBeenCalledWith({ name: "سارة" }));
  });
});
