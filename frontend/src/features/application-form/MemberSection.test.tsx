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
  "رقم بطاقة العلاج :",
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

  it("prefills the e-mail from the signed-in account, read-only, left-to-right", async () => {
    await renderInForm(<MemberSection />, { profile: apiProfile({ email: "doc@x.eg" }) });
    const group = screen.getByRole("group", { name: "البريد الالكتروني :" });
    expect(group).toHaveAttribute("dir", "ltr");
    const boxes = within(group).getAllByRole("textbox");
    expect(boxes[0]).toHaveValue("d");
    expect(boxes[0]).toHaveAttribute("readonly");
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
