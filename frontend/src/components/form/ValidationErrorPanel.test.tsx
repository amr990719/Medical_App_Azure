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

  it("scrolls into view once per failed attempt, never on re-renders or new errors", () => {
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    const { rerender } = render(<ValidationErrorPanel errors={ERRORS} />);
    expect(spy).not.toHaveBeenCalled(); // shown without an attempt: no scroll

    rerender(<ValidationErrorPanel errors={ERRORS} scrollKey={1} />);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });

    rerender(<ValidationErrorPanel errors={[...ERRORS]} scrollKey={1} />);
    rerender(<ValidationErrorPanel errors={ERRORS.slice(1)} scrollKey={1} />);
    expect(spy).toHaveBeenCalledTimes(1); // the list changed while correcting: no scroll

    rerender(<ValidationErrorPanel errors={ERRORS.slice(1)} scrollKey={2} />);
    expect(spy).toHaveBeenCalledTimes(2);
    spy.mockRestore();
  });

  it("never moves the keyboard focus", () => {
    render(<input aria-label="field" />);
    const field = screen.getByLabelText("field");
    field.focus();
    render(<ValidationErrorPanel errors={ERRORS} scrollKey={1} />);
    expect(field).toHaveFocus();
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
