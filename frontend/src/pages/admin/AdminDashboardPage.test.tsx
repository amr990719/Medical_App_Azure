import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { adminHandlers, adminStats, handlers, meAdmin } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const stats = {
  ...adminStats,
  total: 42,
  by_status: { DRAFT: 9, SUBMITTED: 11, UNDER_REVIEW: 8, NEEDS_CORRECTION: 5, APPROVED: 14, REJECTED: 4 },
  receipts_pending: 7,
};

describe("AdminDashboardPage (PROMPT.md §44)", () => {
  it("shows the seven tiles with their §44 labels and the server counts", async () => {
    server.use(handlers.me(meAdmin), handlers.referenceData(), adminHandlers.stats(stats));
    renderApp("/admin/dashboard");

    const tiles = await screen.findByRole("list", { name: "إحصاءات الطلبات" });
    const tile = (label: string) => within(tiles).getByRole("link", { name: new RegExp(label) });
    await within(tiles).findByText("42");
    expect(tile("إجمالي الطلبات")).toHaveTextContent("42");
    expect(tile("بانتظار المراجعة")).toHaveTextContent("11");
    expect(tile("قيد المراجعة")).toHaveTextContent("8");
    expect(tile("يحتاج تصحيح")).toHaveTextContent("5");
    expect(tile("مقبول")).toHaveTextContent("14");
    expect(tile("مرفوض")).toHaveTextContent("4");
    expect(tile("إيصالات بانتظار التأكيد")).toHaveTextContent("7");
  });

  it("links each tile to the matching filtered list", async () => {
    server.use(handlers.me(meAdmin), handlers.referenceData(), adminHandlers.stats(stats));
    renderApp("/admin/dashboard");
    const tiles = await screen.findByRole("list", { name: "إحصاءات الطلبات" });
    await within(tiles).findByText("42");

    expect(within(tiles).getByRole("link", { name: /بانتظار المراجعة/ })).toHaveAttribute(
      "href",
      "/admin/applications?status=SUBMITTED",
    );
    expect(within(tiles).getByRole("link", { name: /إيصالات بانتظار التأكيد/ })).toHaveAttribute(
      "href",
      "/admin/applications?payment_status=PENDING_REVIEW",
    );
    expect(within(tiles).getByRole("link", { name: /إجمالي الطلبات/ })).toHaveAttribute("href", "/admin/applications");
  });
});
