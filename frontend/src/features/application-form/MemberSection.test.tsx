import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, apiApplication, apiProfile } from "@/test/fixtures";
import { renderInForm } from "@/test/renderForm";
import { server } from "@/test/server";
import { MemberSection } from "./MemberSection";

const LABELS_IN_PAPER_ORDER = [
  "الـنـقـابـة :",
  "النقابة الفرعية :",
  "رقم قيد النقابة :",
  "سنة قيد النقابة :",
  "حالة العميل :",
  "أسم العضو :",
  "الديانة :",
  "الرقم القومي :",
  "النوع :",
  "سنة الميلاد :",
  "محافظة السكن :",
  "الحي :",
  "العنوان :",
  "المحمول :",
  "البريد الالكتروني :",
];

describe("MemberSection (PROMPT.md §9.4)", () => {
  it("renders the fields in the paper's order with its labels", async () => {
    await renderInForm(<MemberSection />);
    const section = screen.getByRole("region", { name: "بيانات العضو الأصلي" });
    const text = section.textContent ?? "";
    const positions = LABELS_IN_PAPER_ORDER.map((label) => text.indexOf(label));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });

  it("shows the syndicate registration year where the treatment card number was, and no treatment card", async () => {
    await renderInForm(<MemberSection />);
    const section = screen.getByRole("region", { name: "بيانات العضو الأصلي" });
    expect(section.textContent).not.toContain("بطاقة العلاج");
    const grid = screen.getByTestId("member-grid");
    const year = within(grid).getByRole("textbox", { name: "سنة قيد النقابة :" });
    const cell = year.closest("[class*='md:col-span']");
    // Row 2 is now the registration year and the work status, nothing else.
    expect(cell).toHaveClass("md:col-span-4");
    expect(cell?.nextElementSibling).toHaveClass("md:col-span-8");
    expect(cell?.nextElementSibling).toContainElement(screen.getByRole("radiogroup", { name: "حالة العميل :" }));
    expect(within(grid).getAllByRole("textbox", { name: "سنة قيد النقابة :" })).toHaveLength(1);
  });

  it("uses box radios from reference data for syndicate, work status, religion and gender", async () => {
    await renderInForm(<MemberSection />);
    const syndicate = screen.getByRole("radiogroup", { name: "الـنـقـابـة :" });
    expect(within(syndicate).getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual([
      "بشري",
      "صيدلي",
      "أسنان",
      "بيطري",
    ]);
    expect(within(screen.getByRole("radiogroup", { name: "حالة العميل :" })).getAllByRole("radio")).toHaveLength(3);
    expect(within(screen.getByRole("radiogroup", { name: "الديانة :" })).getAllByRole("radio")).toHaveLength(2);
    expect(within(screen.getByRole("radiogroup", { name: "النوع :" })).getAllByRole("radio")).toHaveLength(2);
  });

  it("keeps the registration-year line short and the work-status boxes on one row", async () => {
    await renderInForm(<MemberSection />);
    const yearLine = screen.getByLabelText("سنة قيد النقابة :").parentElement;
    expect(yearLine).not.toHaveClass("flex-1");
    expect(yearLine).toHaveClass("w-24");
    const workStatus = screen.getByRole("radiogroup", { name: "حالة العميل :" });
    expect(workStatus).toHaveClass("flex-nowrap");
    expect(workStatus).not.toHaveClass("flex-wrap");
  });

  it("offers the 27 governorates from reference data", async () => {
    await renderInForm(<MemberSection />);
    const select = screen.getByRole("combobox", { name: "محافظة السكن :" });
    // + the empty placeholder option
    expect(within(select).getAllByRole("option")).toHaveLength(28);
  });

  it("fills birth year and gender from a pasted national ID", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { user } = await renderInForm(<MemberSection />);
    await user.click(screen.getByLabelText("الرقم 1 من 14"));
    await user.paste("٢٨٥٠٦١٥٠١٠١٢٣٤");
    expect(screen.getByLabelText("سنة الميلاد :")).toHaveValue("1985");
    expect(screen.getByRole("radio", { name: "ذكر" })).toBeChecked();
  });

  it("shows an inline error when the typed birth year contradicts the national ID", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { user } = await renderInForm(<MemberSection />, { profile: apiProfile({ birth_year: 1990 }) });
    await user.click(screen.getByLabelText("الرقم 1 من 14"));
    await user.paste("28506150101234");
    expect(screen.getByText("سنة الميلاد لا تطابق الرقم القومي")).toBeInTheDocument();
  });

  it("shows the account e-mail as read-only LTR text on one dotted line (no character boxes)", async () => {
    await renderInForm(<MemberSection />, { profile: apiProfile({ email: "doctor.name@example.eg" }) });
    const email = screen.getByLabelText("البريد الالكتروني :");
    expect(email).toHaveValue("doctor.name@example.eg");
    expect(email).toHaveAttribute("readonly");
    expect(email).toHaveAttribute("dir", "ltr");
    expect(email).toHaveClass("w-full", "border-dotted");
    expect(email).not.toHaveClass("border-dashed");
    expect(screen.queryByRole("group", { name: "البريد الالكتروني :" })).not.toBeInTheDocument();
    expect(document.querySelectorAll(".paper-box")).toHaveLength(14); // only the national-ID boxes
  });

  it("keeps the e-mail read-only: typing does not change it", async () => {
    const { user } = await renderInForm(<MemberSection />, { profile: apiProfile({ email: "doc@x.eg" }) });
    const email = screen.getByLabelText("البريد الالكتروني :");
    await user.type(email, "zzz");
    expect(email).toHaveValue("doc@x.eg");
  });

  it("keeps LTR inputs for years and the mobile number", async () => {
    await renderInForm(<MemberSection />);
    expect(screen.getByLabelText("المحمول :")).toHaveAttribute("dir", "ltr");
    expect(screen.getByLabelText("سنة قيد النقابة :")).toHaveAttribute("dir", "ltr");
  });

  it("stacks one field per row below 768px (12-column grid only from md)", async () => {
    await renderInForm(<MemberSection />);
    const grid = screen.getByTestId("member-grid");
    expect(grid.className).toMatch(/\bgrid-cols-1\b/);
    expect(grid.className).toMatch(/\bmd:grid-cols-12\b/);
  });

  it("is read-only for a submitted application", async () => {
    await renderInForm(<MemberSection />, { app: apiApplication({ status: "SUBMITTED", is_editable: false }) });
    expect(screen.getByLabelText("النقابة الفرعية :")).toHaveAttribute("readonly");
    expect(screen.getByRole("radio", { name: "بشري" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "محافظة السكن :" })).toBeDisabled();
  });
});
