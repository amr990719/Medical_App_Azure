import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { apiApplication } from "@/test/fixtures";
import { renderInForm } from "@/test/renderForm";
import { DeclarationSection } from "./DeclarationSection";

const FIRST =
  "بأن جميع البيانات بعاليه صحيحة وكذلك صور المستفيدين، وأنها مطابقة لشروط الاشتراك بالمشروع، وإذا ثبت عكس ذلك أتحمل المسئولية المالية والقانونية فورا مع عدم رد قيمة الاشتراك وأتحمل كافة التكاليف، وللمشروع الحق في اتخاذ أي إجراء مناسب لذلك.";
const SECOND =
  "وأقر بالموافقة على النظام العلاجي الذي يسير عليه المشروع وكذلك أية تعديلات تتم أثناء العام تصدر من إدارة المشروع، وأتبرع تكافلا بمبلغ اشتراكي لعلاج زملائي المشتركين وأتعاون معهم في سداد قيمة العلاج .";

describe("DeclarationSection (owner wording of 2026-10-28)", () => {
  it("shows the declaration exactly, with the name input on the dotted line", async () => {
    await renderInForm(<DeclarationSection />, { app: apiApplication({ declaration_name: "أحمد محمد" }) });
    const section = screen.getByRole("region", { name: "إقــــــــرار" });
    const input = screen.getByLabelText("اسم المقر");
    const first = input.closest("p");
    expect(first?.textContent?.replace(/\s+/g, " ").trim()).toBe(`أقر أنا / أحمد محمد ${FIRST}`);
    expect(first?.textContent?.startsWith("أقر أنا /")).toBe(true);
    expect(screen.getByText(SECOND).tagName).toBe("P");
    expect(input).toHaveValue("أحمد محمد");
    expect(input).toHaveClass("border-dotted", "inline-block", "w-full");
    expect(input).not.toHaveClass("border-dashed");
    expect(section.textContent).not.toContain("\\");
  });

  it("drops the superseded wording and the signature label", async () => {
    await renderInForm(<DeclarationSection />);
    const text = screen.getByRole("region", { name: "إقــــــــرار" }).textContent ?? "";
    expect(text).not.toContain("المقر بما فيه");
    expect(text).not.toContain("وأن الأولاد في الدراسة");
    expect(text).not.toContain("لا يجوز استفادة الابن بعد التخرج");
    expect(text).not.toContain("لجنة العلاج العليا");
    expect(screen.queryByRole("region", { name: "إقــــــــرار" })?.querySelector("u")).toBeNull();
  });

  it("keeps the declared name editable and read-only for a submitted application", async () => {
    await renderInForm(<DeclarationSection />, { app: apiApplication({ status: "SUBMITTED", is_editable: false }) });
    expect(screen.getByLabelText("اسم المقر")).toHaveAttribute("readonly");
  });

  it("prints the declared name as text, because the inline input clips a long name on paper", async () => {
    const long = "عبد العزيز مصطفى إبراهيم عبد الغفار الشناوي";
    await renderInForm(<DeclarationSection />, { app: apiApplication({ declaration_name: long }) });
    const input = screen.getByLabelText("اسم المقر");
    expect(input).toHaveValue(long);
    expect(input).toHaveClass("print:hidden");
    const printed = input.parentElement?.querySelector("[data-print-value]");
    expect(printed).toHaveTextContent(long);
    expect(printed).toHaveClass("hidden", "print:inline", "border-dotted");
  });
});
