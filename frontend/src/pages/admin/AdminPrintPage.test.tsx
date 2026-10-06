import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ADMIN_APP_ID, API, apiAdminDetail, handlers, meAdmin } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const detail = apiAdminDetail();

describe("AdminPrintPage", () => {
  it("prints the paper form from the admin endpoint with the reference banner, masked by default", async () => {
    const reveals: (string | null)[] = [];
    server.use(
      handlers.me(meAdmin),
      handlers.referenceData(),
      http.get(`${API}/admin/applications/${ADMIN_APP_ID}/`, ({ request }) => {
        reveals.push(new URL(request.url).searchParams.get("reveal_national_id"));
        return HttpResponse.json(detail);
      }),
    );
    renderApp(`/admin/applications/${ADMIN_APP_ID}/print`);

    expect(await screen.findByText("MED-2026-000001")).toBeInTheDocument();
    const name = await screen.findByLabelText("أسم العضو :");
    expect(name).toHaveValue("أحمد محمد علي حسن");
    expect(name).toHaveAttribute("readonly");
    expect(screen.getByDisplayValue("28•••••••••234")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "العودة إلى الطلب" })).toHaveAttribute(
      "href",
      `/admin/applications/${ADMIN_APP_ID}`,
    );
    expect(screen.getByRole("button", { name: "طباعة" })).toBeInTheDocument();
    expect(reveals.every((r) => r === null)).toBe(true);
    expect(within(document.body).queryByText("حفظ تلقائي")).not.toBeInTheDocument();
  });
});
