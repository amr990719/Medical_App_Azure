import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ValidationErrorPanel } from "./ValidationErrorPanel";

const ERRORS = [
  { message: "يرجى تحديد حالة العمل", field: "member.work_status" },
  { message: "يرجى إرفاق صورة وجه البطاقة الشخصية", field: "documents.NATIONAL_ID_FRONT" },
  { message: "اسم المقر يجب أن يطابق اسم العضو" },
];

describe("ValidationErrorPanel", () => {
  it("shows the title and lists every error", () => {
    render(<ValidationErrorPanel errors={ERRORS} />);
    const panel = screen.getByRole("alert");
    expect(panel).toHaveTextContent("يرجى تصحيح الأخطاء التالية قبل المتابعة:");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    for (const { message } of ERRORS) expect(panel).toHaveTextContent(message);
  });

  it("scrolls itself into view on mount", () => {
    const spy = vi.spyOn(Element.prototype, "scrollIntoView");
    render(<ValidationErrorPanel errors={ERRORS} />);
    expect(spy).toHaveBeenCalled();
  });

  it("renders nothing without errors", () => {
    const { container } = render(<ValidationErrorPanel errors={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("has the red start border", () => {
    render(<ValidationErrorPanel errors={ERRORS} />);
    expect(screen.getByRole("alert").className).toContain("border-s-4");
  });
});
