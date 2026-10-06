import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/client";
import { toCamel } from "@/api/case";
import { feeQuote } from "@/test/fixtures";
import { FeeSummaryPanel } from "./FeeSummaryPanel";

const quote = toCamel(feeQuote);

describe("FeeSummaryPanel", () => {
  it("renders the server quote rows, tier and total", () => {
    render(<FeeSummaryPanel quote={quote} />);
    const panel = screen.getByRole("region", { name: "ملخص الرسوم" });
    expect(within(panel).getByText("الدرجة 3")).toBeInTheDocument();
    const rows = within(panel).getAllByRole("row");
    expect(rows.map((r) => r.textContent)).toEqual(
      expect.arrayContaining([
        expect.stringContaining("العضو الأصلي"),
        expect.stringContaining("رسوم إدارية775 ج.م"),
      ]),
    );
    const total = within(panel).getByText("الإجمالي").closest("tr")!;
    expect(total).toHaveTextContent("3٬025 ج.م");
  });

  it("shows a row note when the server sends one", () => {
    const withNote = { ...quote, breakdown: [{ label: "أم", fee: 500, note: "تم تطبيق حد السن" }] };
    render(<FeeSummaryPanel quote={withNote} />);
    expect(screen.getByText("تم تطبيق حد السن")).toBeInTheDocument();
  });

  it("shows a skeleton while loading", () => {
    render(<FeeSummaryPanel isLoading />);
    const panel = screen.getByRole("region", { name: "ملخص الرسوم" });
    expect(panel).toHaveAttribute("aria-busy", "true");
    expect(panel.querySelectorAll("[data-skeleton]").length).toBeGreaterThan(0);
  });

  it("shows the server error message when the quote is not valid", () => {
    const invalid = { ...quote, isValid: false, errorMessage: "سنة قيد النقابة غير صحيحة", total: 0 };
    render(<FeeSummaryPanel quote={invalid} />);
    expect(screen.getByRole("alert")).toHaveTextContent("سنة قيد النقابة غير صحيحة");
    expect(screen.queryByText("الإجمالي")).toBeNull();
  });

  it("shows a request error", () => {
    render(<FeeSummaryPanel error={new ApiError(400, "VALIDATION_ERROR", "لا يوجد جدول رسوم مفعل")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("لا يوجد جدول رسوم مفعل");
  });

  it("takes the form page title with the fiscal year and a teal start border (§17.6)", () => {
    render(
      <FeeSummaryPanel quote={quote} title="ملخص الاشتراك — السنة المالية 2026" accent="teal" />,
    );
    const panel = screen.getByRole("region", { name: "ملخص الاشتراك — السنة المالية 2026" });
    expect(panel.className).toMatch(/border-s-teal/);
  });

  it("has a banana header on the payment page (§18)", () => {
    render(<FeeSummaryPanel quote={quote} accent="banana" />);
    const heading = screen.getByRole("heading", { name: "ملخص الرسوم" });
    expect(heading.parentElement?.className).toMatch(/bg-banana/);
  });
});
