import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { APP_ID, handlers, meAdmin, meDoctor } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

describe("routes: application printing is retired (2026-10-28)", () => {
  it("does not serve the doctor's print view", async () => {
    server.use(handlers.me(meDoctor), handlers.referenceData());
    renderApp(`/application/${APP_ID}/print`);
    expect(await screen.findByRole("heading", { name: "الصفحة غير موجودة" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /طباعة/ })).toBeNull();
  });

  it("does not serve the admin print view", async () => {
    server.use(handlers.me(meAdmin), handlers.referenceData());
    renderApp(`/admin/applications/${APP_ID}/print`);
    expect(await screen.findByRole("heading", { name: "الصفحة غير موجودة" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /طباعة/ })).toBeNull();
  });
});
