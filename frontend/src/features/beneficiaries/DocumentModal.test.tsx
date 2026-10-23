import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { Beneficiary, DocumentRequirement, DocumentSummary } from "@/api/types";
import { API, PHOTO_CHILD_EXEMPT_HINT, PHOTO_HINT, apiDocument } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { DocumentModal } from "./DocumentModal";

const FRONT = "بطاقة الرقم القومي للمستفيد (وجه)";
const BACK = "بطاقة الرقم القومي للمستفيد (ظهر)";
const PHOTO = "صورة شخصية للمستفيد بخلفية بيضاء";

const stored = (overrides: Partial<DocumentSummary>): DocumentSummary => ({
  id: "d9",
  documentType: "MARRIAGE_CERTIFICATE",
  beneficiaryId: "b1",
  originalFilename: "marriage.jpg",
  contentType: "image/jpeg",
  fileSize: 1000,
  scanStatus: "SKIPPED",
  createdAt: "2026-10-05T10:00:00+03:00",
  contentUrl: "/api/v1/documents/d9/content/",
  ...overrides,
});

const wife: Beneficiary = {
  id: "b1",
  rowNumber: 1,
  kinship: "WIFE",
  fullName: "سارة محمود علي",
  birthYear: 1990,
  nationalId: "29001011234567",
  isFirstTime: true,
  isActive: true,
  requiredDocuments: [
    { type: "BENEFICIARY_NATIONAL_ID", required: true, label: FRONT, ocrCapable: true },
    { type: "BENEFICIARY_NATIONAL_ID_BACK", required: true, label: BACK, ocrCapable: false },
    { type: "MARRIAGE_CERTIFICATE", required: true, label: "شهادة الزواج", ocrCapable: false },
    { type: "INSURANCE_PRINT", required: false, label: "برينت تأميني", ocrCapable: false },
    { type: "BENEFICIARY_PERSONAL_PHOTO", required: true, label: PHOTO, ocrCapable: false, imagesOnly: true, hints: [PHOTO_HINT] },
  ],
  documents: [stored({})],
  updatedAt: "2026-10-05T10:00:00+03:00",
};

function renderModal(beneficiary: Beneficiary = wife, extra: Partial<Parameters<typeof DocumentModal>[0]> = {}) {
  const onClose = vi.fn();
  const view = renderWithProviders(
    <DocumentModal open applicationId="a1" beneficiary={beneficiary} onClose={onClose} {...extra} />,
  );
  return { ...view, onClose };
}

function captureUploads() {
  const forms: FormData[] = [];
  server.use(
    http.post(`${API}/applications/a1/documents/`, async ({ request }) => {
      const form = await request.formData();
      forms.push(form);
      return HttpResponse.json(
        apiDocument({
          id: `d-${forms.length}`,
          document_type: form.get("document_type") as DocumentSummary["documentType"],
          beneficiary_id: (form.get("beneficiary_id") as string | null) ?? null,
        }),
        { status: 201 },
      );
    }),
  );
  return forms;
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
      FRONT,
      BACK,
      "شهادة الزواج",
      "برينت تأميني",
      PHOTO,
    ]);
    expect(within(slots[0]!).getByText("مطلوب")).toBeInTheDocument();
    expect(within(slots[3]!).getByText("اختياري")).toBeInTheDocument();
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
    const withSides: Beneficiary = {
      ...wife,
      documents: [
        ...wife.documents,
        stored({ id: "d-nid", documentType: "BENEFICIARY_NATIONAL_ID", contentUrl: "/x" }),
        stored({ id: "d-back", documentType: "BENEFICIARY_NATIONAL_ID_BACK", contentUrl: "/y" }),
      ],
    };
    const onExtracted = vi.fn();
    const { user } = renderModal(withSides, { onExtracted });
    const scans = screen.getAllByRole("button", { name: "مسح تلقائي" });
    expect(scans).toHaveLength(1); // the back side and the marriage certificate have no extraction
    expect(within(screen.getByRole("group", { name: FRONT })).getByRole("button", { name: "مسح تلقائي" })).toBe(scans[0]);
    await user.click(scans[0]!);
    await waitFor(() => expect(onExtracted).toHaveBeenCalledWith({ name: "سارة" }));
  });

  // --- national ID front and back -------------------------------------------------------------

  it("keeps an existing front upload while the back side is still missing", () => {
    const frontOnly: Beneficiary = {
      ...wife,
      documents: [stored({ id: "d-front", documentType: "BENEFICIARY_NATIONAL_ID", originalFilename: "front.jpg" })],
    };
    renderModal(frontOnly);
    expect(within(screen.getByRole("group", { name: FRONT })).getByText("✓ تم الإرفاق: front.jpg")).toBeInTheDocument();
    const back = screen.getByRole("group", { name: BACK });
    expect(within(back).queryByText(/تم الإرفاق/)).toBeNull();
    expect(within(back).getByRole("button", { name: "اختيار ملف" })).toBeInTheDocument();
  });

  it("uploads and replaces each side independently", async () => {
    const forms = captureUploads();
    const frontOnly: Beneficiary = {
      ...wife,
      documents: [stored({ id: "d-front", documentType: "BENEFICIARY_NATIONAL_ID", originalFilename: "front.jpg" })],
    };
    const { user } = renderModal(frontOnly);
    await user.upload(screen.getByLabelText(BACK, { selector: "input" }), new File(["b"], "back.png", { type: "image/png" }));
    await waitFor(() => expect(forms).toHaveLength(1));
    expect(forms[0]!.get("document_type")).toBe("BENEFICIARY_NATIONAL_ID_BACK");
    expect(forms[0]!.get("beneficiary_id")).toBe("b1");
    // The front still shows its own file; replacing it sends the FRONT type only.
    expect(within(screen.getByRole("group", { name: FRONT })).getByText("✓ تم الإرفاق: front.jpg")).toBeInTheDocument();
    const front = screen.getByRole("group", { name: FRONT });
    expect(within(front).getByRole("button", { name: "استبدال" })).toBeInTheDocument();
    await user.upload(screen.getByLabelText(FRONT, { selector: "input" }), new File(["f"], "front2.png", { type: "image/png" }));
    await waitFor(() => expect(forms).toHaveLength(2));
    expect(forms[1]!.get("document_type")).toBe("BENEFICIARY_NATIONAL_ID");
    expect(within(screen.getByRole("group", { name: BACK })).getByText(/تم الإرفاق/)).toBeInTheDocument();
  });

  // --- personal photo ---------------------------------------------------------------------------

  it("shows the white-background guidance and accepts images only for the photo", () => {
    const son: Beneficiary = {
      ...wife,
      kinship: "SON_MINOR",
      requiredDocuments: [
        {
          type: "BENEFICIARY_PERSONAL_PHOTO",
          required: false,
          label: PHOTO,
          ocrCapable: false,
          imagesOnly: true,
          hints: [PHOTO_HINT, PHOTO_CHILD_EXEMPT_HINT],
        },
      ],
      documents: [],
    };
    renderModal(son);
    const slot = screen.getByRole("group", { name: PHOTO });
    expect(slot).toHaveTextContent(PHOTO_HINT);
    expect(slot).toHaveTextContent(PHOTO_CHILD_EXEMPT_HINT);
    const input = within(slot).getByLabelText(PHOTO, { selector: "input" });
    expect(input).toHaveAttribute("accept", "image/jpeg,image/png,image/webp");
    expect(input).toHaveAccessibleDescription(`${PHOTO_HINT} ${PHOTO_CHILD_EXEMPT_HINT}`);
  });

  it("does not show the under-3 note outside SON_MINOR (the server sends it only there)", () => {
    renderModal();
    expect(screen.getByRole("group", { name: PHOTO })).not.toHaveTextContent(PHOTO_CHILD_EXEMPT_HINT);
  });

  // --- member-owned slot opened from the mother's row ------------------------------------------

  const memberCertificate: DocumentRequirement = {
    type: "MEMBER_BIRTH_CERTIFICATE",
    required: true,
    label: "شهادة ميلاد العضو الأصلي لإثبات صلة القرابة بالأم",
    ocrCapable: false,
    hints: ["مطلوبة لإضافة الأم: شهادة ميلاد العضو الأصلي نفسه، ولا تغني عنها شهادة ميلاد الأم."],
  };
  const mother: Beneficiary = {
    ...wife,
    kinship: "MOTHER",
    fullName: "فاطمة علي أحمد",
    requiredDocuments: wife.requiredDocuments.slice(0, 2),
    documents: [],
  };

  it("offers the member's own birth certificate in a separate member section", async () => {
    const forms = captureUploads();
    const { user } = renderModal(mother, { memberSlots: [memberCertificate] });
    const section = screen.getByRole("region", { name: "مستند خاص بالعضو الأصلي" });
    const slot = within(section).getByRole("group", { name: memberCertificate.label });
    expect(slot).toHaveTextContent("ولا تغني عنها شهادة ميلاد الأم");
    expect(within(slot).queryByRole("button", { name: "مسح تلقائي" })).toBeNull();
    await user.upload(within(slot).getByLabelText(memberCertificate.label, { selector: "input" }), new File(["c"], "me.png", { type: "image/png" }));
    await waitFor(() => expect(forms).toHaveLength(1));
    expect(forms[0]!.get("document_type")).toBe("MEMBER_BIRTH_CERTIFICATE");
    expect(forms[0]!.get("beneficiary_id")).toBeNull(); // member-owned, never the mother's
  });

  it("shows an already uploaded member certificate and has no member section otherwise", () => {
    const uploaded = stored({ id: "d-mbc", documentType: "MEMBER_BIRTH_CERTIFICATE", beneficiaryId: null, originalFilename: "me.jpg" });
    const { unmount } = renderModal(mother, {
      memberSlots: [memberCertificate],
      memberDocuments: { MEMBER_BIRTH_CERTIFICATE: uploaded },
    });
    expect(screen.getByText("✓ تم الإرفاق: me.jpg")).toBeInTheDocument();
    unmount();
    renderModal(wife);
    expect(screen.queryByRole("region", { name: "مستند خاص بالعضو الأصلي" })).toBeNull();
  });
});
