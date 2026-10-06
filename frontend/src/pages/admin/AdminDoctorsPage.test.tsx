import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, adminDoctor, adminDoctors, handlers, meAdmin } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

function serveList() {
  const queries: URLSearchParams[] = [];
  server.use(
    handlers.me(meAdmin),
    handlers.referenceData(),
    http.get(`${API}/admin/doctors/`, ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json(adminDoctors);
    }),
  );
  return queries;
}

const listed = adminDoctors.results.find((d) => d.email === "doctor@dev.local")!;

describe("AdminDoctorsPage", () => {
  it("lists members with masked national IDs and links to their page", async () => {
    serveList();
    renderApp("/admin/doctors");
    const table = await screen.findByRole("table", { name: "قائمة الأعضاء" });
    const row = (await within(table).findByText(listed.email)).closest("tr")!;
    expect(row).toHaveTextContent(listed.masked_national_id);
    expect(row).not.toHaveTextContent("28506150199991");
    expect(within(row).getByRole("link", { name: listed.full_name })).toHaveAttribute("href", `/admin/doctors/${listed.id}`);
  });

  it("searches on the server", async () => {
    const queries = serveList();
    const { user } = renderApp("/admin/doctors");
    await screen.findByRole("table", { name: "قائمة الأعضاء" });
    await user.type(screen.getByRole("searchbox", { name: "بحث" }), "منى");
    await user.click(screen.getByRole("button", { name: "بحث" }));
    await waitFor(() => expect(Object.fromEntries(queries[queries.length - 1]!)).toMatchObject({ search: "منى" }));
  });
});

describe("AdminDoctorDetailPage", () => {
  it("shows the profile and the member's applications", async () => {
    server.use(
      handlers.me(meAdmin),
      handlers.referenceData(),
      http.get(`${API}/admin/doctors/${adminDoctor.id}/`, () => HttpResponse.json(adminDoctor)),
    );
    renderApp(`/admin/doctors/${adminDoctor.id}`);
    expect(await screen.findByRole("heading", { level: 1, name: adminDoctor.full_name })).toBeInTheDocument();
    expect(screen.getByText(adminDoctor.masked_national_id)).toBeInTheDocument();
    const app = adminDoctor.applications[0]!;
    expect(screen.getByRole("link", { name: app.reference_number! })).toHaveAttribute("href", `/admin/applications/${app.id}`);
  });
});
