import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, apiAdminRow, handlers, meAdmin, page, type ApiAdminRow } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const row = apiAdminRow({
  id: "a1",
  reference_number: "MED-2026-000123",
  doctor_name: "أحمد علي",
  syndicate_type: "HUMAN_MEDICINE",
  status: "UNDER_REVIEW",
  payment_status: "PENDING_REVIEW",
  submitted_at: "2026-10-03T09:15:00+03:00",
  total: 3025,
});

/** Serves the list and records every query string the page sent. */
function serveList(rows: ApiAdminRow[] = [row], count = rows.length) {
  const queries: URLSearchParams[] = [];
  server.use(
    handlers.me(meAdmin),
    handlers.referenceData(),
    http.get(`${API}/admin/applications/`, ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json({ ...page(rows), count });
    }),
  );
  return queries;
}

const lastQuery = (queries: URLSearchParams[]) => Object.fromEntries(queries[queries.length - 1] ?? []);

describe("AdminApplicationsPage (PROMPT.md §44, §45)", () => {
  it("renders the §44 columns with formatted values", async () => {
    serveList();
    renderApp("/admin/applications");
    const table = await screen.findByRole("table", { name: "قائمة الطلبات" });
    const headers = within(table).getAllByRole("columnheader").map((th) => th.textContent?.trim());
    expect(headers).toEqual(["رقم الطلب", "مقدم الطلب", "النقابة", "الحالة", "الدفع", "تاريخ التقديم", "الإجمالي"]);

    const cells = within(await within(table).findByRole("row", { name: /MED-2026-000123/ })).getAllByRole("cell");
    expect(cells.map((td) => td.textContent?.trim())).toEqual([
      "MED-2026-000123",
      "أحمد علي",
      "بشري",
      "قيد المراجعة",
      "بانتظار التأكيد",
      "٣ أكتوبر ٢٠٢٦",
      "3٬025 ج.م",
    ]);
    expect(within(table).getByRole("link", { name: "MED-2026-000123" })).toHaveAttribute("href", "/admin/applications/a1");
  });

  it("sends the URL filters to the server and reflects new filters in the URL", async () => {
    const queries = serveList();
    const { router, user } = renderApp("/admin/applications?status=SUBMITTED");
    await screen.findByRole("row", { name: /MED-2026-000123/ });
    expect(lastQuery(queries)).toMatchObject({ status: "SUBMITTED" });
    expect(screen.getByRole("combobox", { name: "الحالة" })).toHaveValue("SUBMITTED");

    await user.selectOptions(screen.getByRole("combobox", { name: "الدفع" }), "PENDING_REVIEW");
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ status: "SUBMITTED", payment_status: "PENDING_REVIEW" }));
    expect(router.state.location.search).toContain("payment_status=PENDING_REVIEW");

    await user.selectOptions(screen.getByRole("combobox", { name: "المحافظة" }), "الجيزة");
    await user.selectOptions(screen.getByRole("combobox", { name: "النقابة" }), "PHARMACY");
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ governorate: "الجيزة", syndicate_type: "PHARMACY" }));
  });

  it("searches on submit and normalizes Arabic digits", async () => {
    const queries = serveList();
    const { user } = renderApp("/admin/applications");
    await screen.findByRole("row", { name: /MED-2026-000123/ });

    await user.type(screen.getByRole("searchbox", { name: "بحث" }), "٢٩•••••••••١٢٣");
    await user.click(screen.getByRole("button", { name: "بحث" }));
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ search: "29•••••••••123" }));
  });

  it("sorts on the server when a sortable header is clicked", async () => {
    const queries = serveList();
    const { user } = renderApp("/admin/applications");
    await screen.findByRole("row", { name: /MED-2026-000123/ });

    await user.click(screen.getByRole("button", { name: "ترتيب حسب الإجمالي" }));
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ ordering: "total" }));
    expect(screen.getByRole("columnheader", { name: /الإجمالي/ })).toHaveAttribute("aria-sort", "ascending");

    await user.click(screen.getByRole("button", { name: "ترتيب حسب الإجمالي" }));
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ ordering: "-total" }));
    expect(screen.getByRole("columnheader", { name: /الإجمالي/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("paginates on the server (25 per page)", async () => {
    const queries = serveList([row], 60);
    const { user } = renderApp("/admin/applications");
    await screen.findByText("صفحة 1 من 3");
    expect(screen.getByText("60 طلب")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "السابق" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "التالي" }));
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ page: "2" }));
    expect(await screen.findByText("صفحة 2 من 3")).toBeInTheDocument();
  });

  it("goes back to page 1 when a filter changes", async () => {
    const queries = serveList([row], 60);
    const { user } = renderApp("/admin/applications?page=3");
    await screen.findByText("صفحة 3 من 3");
    await user.selectOptions(screen.getByRole("combobox", { name: "الحالة" }), "APPROVED");
    await waitFor(() => expect(lastQuery(queries)).toMatchObject({ status: "APPROVED" }));
    expect(lastQuery(queries).page).toBeUndefined();
  });

  it("shows an empty state", async () => {
    serveList([]);
    renderApp("/admin/applications?search=zzz");
    expect(await screen.findByText("لا توجد طلبات مطابقة.")).toBeInTheDocument();
  });
});
