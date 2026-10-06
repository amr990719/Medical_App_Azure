import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API, APP_ID, apiApplication, apiBeneficiary, apiDocument, SPOUSE_REQUIREMENTS } from "@/test/fixtures";
import { renderInForm } from "@/test/renderForm";
import { server } from "@/test/server";
import { BeneficiaryTable } from "./BeneficiaryTable";

const wifeDocs = SPOUSE_REQUIREMENTS.map((req, i) =>
  apiDocument({ id: `d${i}`, document_type: req.type as never, beneficiary_id: "b-wife" }),
);

function mockViewport(desktop: boolean) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) =>
      ({
        matches: desktop,
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("BeneficiaryTable (PROMPT.md §9.5)", () => {
  it("has exactly max_beneficiaries rows with the paper's columns", async () => {
    await renderInForm(<BeneficiaryTable />);
    const table = screen.getByRole("table", { name: "بيانات المستفيدين مع العضو الأصلى" });
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["م", "درجة القرابة", "اسم المستفيد", "سنة الميلاد", "الرقم القومي"]);
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 10);
  });

  it("prints the full name as wrapping text, because an input clips a long name on paper", async () => {
    const long = "فاطمة الزهراء عبد الرحمن محمود الشناوي";
    await renderInForm(<BeneficiaryTable />, { app: apiApplication({ beneficiaries: [apiBeneficiary({ full_name: long })] }) });
    const input = screen.getByLabelText("اسم المستفيد — المستفيد رقم 1");
    expect(input).toHaveValue(long);
    expect(input).toHaveClass("print:hidden");
    const printed = input.parentElement?.querySelector("[data-print-value]");
    expect(printed).toHaveTextContent(long);
    expect(printed).toHaveClass("hidden", "print:block");
  });

  it("shows the paperclip only once a kinship is set: grey while documents are missing, green when complete", async () => {
    const incomplete = apiBeneficiary({ documents: wifeDocs.slice(0, 1) });
    const complete = apiBeneficiary({ id: "b-2", row_number: 2, full_name: "سارة", documents: wifeDocs });
    await renderInForm(<BeneficiaryTable />, { app: apiApplication({ beneficiaries: [incomplete, complete] }) });
    expect(screen.getByRole("button", { name: /مستندات المستفيد رقم 1/ })).toHaveAttribute("data-state", "missing");
    expect(screen.getByRole("button", { name: /مستندات المستفيد رقم 2/ })).toHaveAttribute("data-state", "complete");
    expect(screen.queryByRole("button", { name: /مستندات المستفيد رقم 3/ })).toBeNull();
  });

  it("opens the DocumentModal for that beneficiary with the server's slots", async () => {
    const { user } = await renderInForm(<BeneficiaryTable />, {
      app: apiApplication({ beneficiaries: [apiBeneficiary()] }),
    });
    await user.click(screen.getByRole("button", { name: /مستندات المستفيد رقم 1/ }));
    const dialog = screen.getByRole("dialog", { name: "مستندات المستفيد: منى سعيد عبد الله" });
    expect(within(dialog).getByText("شهادة الزواج")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks before changing the kinship of a row with documents, and clears them after confirming", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(apiBeneficiary({ kinship: "MOTHER", documents: [] }));
      }),
    );
    const { user } = await renderInForm(<BeneficiaryTable />, {
      app: apiApplication({ beneficiaries: [apiBeneficiary({ documents: wifeDocs })] }),
    });
    const select = screen.getByRole("combobox", { name: "درجة القرابة — المستفيد رقم 1" });

    await user.selectOptions(select, "MOTHER");
    let dialog = screen.getByRole("dialog", { name: "تغيير درجة القرابة؟" });
    await user.click(within(dialog).getByRole("button", { name: "إلغاء" }));
    expect(select).toHaveValue("WIFE");
    expect(bodies).toEqual([]);

    await user.selectOptions(select, "MOTHER");
    dialog = screen.getByRole("dialog", { name: "تغيير درجة القرابة؟" });
    await user.click(within(dialog).getByRole("button", { name: "تغيير وحذف المستندات" }));
    expect(select).toHaveValue("MOTHER");
    expect(screen.getByRole("button", { name: /مستندات المستفيد رقم 1/ })).toHaveAttribute("data-state", "missing");
    await waitFor(() => expect(bodies).toEqual([{ kinship: "MOTHER" }]));
  });

  it("changes the kinship of a row without documents immediately", async () => {
    server.use(
      http.patch(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, () =>
        HttpResponse.json(apiBeneficiary({ kinship: "MOTHER" })),
      ),
    );
    const { user } = await renderInForm(<BeneficiaryTable />, {
      app: apiApplication({ beneficiaries: [apiBeneficiary()] }),
    });
    await user.selectOptions(screen.getByRole("combobox", { name: "درجة القرابة — المستفيد رقم 1" }), "MOTHER");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("deletes a cleared beneficiary after confirmation", async () => {
    let deleted = false;
    server.use(
      http.delete(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = await renderInForm(<BeneficiaryTable />, {
      app: apiApplication({ beneficiaries: [apiBeneficiary()] }),
    });
    await user.click(screen.getByRole("button", { name: "مسح بيانات المستفيد رقم 1" }));
    const dialog = screen.getByRole("dialog", { name: "حذف المستفيد؟" });
    expect(dialog).toHaveTextContent("منى سعيد عبد الله");
    await user.click(within(dialog).getByRole("button", { name: "حذف المستفيد" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(screen.getByRole("textbox", { name: "اسم المستفيد — المستفيد رقم 1" })).toHaveValue("");
  });

  it("shows one card per beneficiary below 768px instead of the table", async () => {
    mockViewport(false);
    await renderInForm(<BeneficiaryTable />, { app: apiApplication({ beneficiaries: [apiBeneficiary()] }) });
    expect(screen.queryByRole("table")).toBeNull();
    const cards = screen.getAllByRole("group", { name: /^المستفيد رقم \d+$/ });
    expect(cards).toHaveLength(10);
    expect(within(cards[0]!).getByRole("textbox", { name: "اسم المستفيد — المستفيد رقم 1" })).toHaveValue(
      "منى سعيد عبد الله",
    );
  });

  it("always renders the table when asked for the print layout", async () => {
    mockViewport(false);
    await renderInForm(<BeneficiaryTable layout="table" />);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
