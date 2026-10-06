import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, adminFeeSchedules, handlers, meAdmin, page, type ApiFeeSchedule } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const fy2026 = adminFeeSchedules.results.find((s) => s.fiscal_year === 2026 && s.is_active) as ApiFeeSchedule;
const locked: ApiFeeSchedule = { ...fy2026, locked_at: "2026-10-03T09:15:00+03:00" };

function serve(schedules: ApiFeeSchedule[] = [locked]) {
  const posts: unknown[] = [];
  let current = schedules;
  server.use(
    handlers.me(meAdmin),
    handlers.referenceData(),
    http.get(`${API}/admin/fee-schedules/`, () => HttpResponse.json(page(current))),
    http.post(`${API}/admin/fee-schedules/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      posts.push(body);
      const created = { ...fy2026, ...body, id: "new-version", version: 2, is_active: true, locked_at: null } as ApiFeeSchedule;
      current = [created, ...current.map((s) => ({ ...s, is_active: false }))];
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  return posts;
}

async function open() {
  const view = renderApp("/admin/fee-schedules");
  await screen.findByRole("heading", { level: 1, name: "جداول الرسوم" });
  return view;
}

const tierRow = (table: HTMLElement, tier: number) =>
  within(table)
    .getByRole("row", { name: new RegExp(`الشريحة ${tier}`) })
    .querySelectorAll("td");

describe("AdminFeeSchedulesPage (PROMPT.md §17.1, §44)", () => {
  it("shows the active FY 2026 schedule with the exact amounts", async () => {
    serve();
    await open();
    const table = await screen.findByRole("table", { name: /السنة المالية 2026 — الإصدار 1/ });
    const headers = within(table).getAllByRole("columnheader").map((th) => th.textContent?.trim());
    expect(headers).toEqual(["الشريحة", "العضو الأصلي", "الزوج / الزوجة", "الأبناء", "ابن جامعي / خريج", "الوالدان"]);
    const amounts = (tier: number) => Array.from(tierRow(table, tier)).map((td) => td.textContent?.trim());
    expect(amounts(1)).toEqual(["600", "800", "500", "1٬200", "1٬050"]);
    expect(amounts(2)).toEqual(["700", "950", "550", "1٬400", "1٬200"]);
    expect(amounts(3)).toEqual(["750", "1٬000", "550", "1٬500", "1٬300"]);
    expect(amounts(4)).toEqual(["850", "1٬050", "600", "1٬750", "1٬400"]);

    const settings = screen.getByRole("region", { name: "إعدادات الحساب" });
    expect(within(settings).getByText("رسوم إدارية (العضو فقط)").nextElementSibling).toHaveTextContent("150 ج.م");
    expect(within(settings).getByText("رسوم إدارية (مع مستفيدين)").nextElementSibling).toHaveTextContent("175 ج.م");
    expect(within(settings).getByText("سن تطبيق السقف").nextElementSibling).toHaveTextContent("70");
    expect(within(settings).getByText("قيمة السقف").nextElementSibling).toHaveTextContent("500 ج.م");
  });

  it("labels the tiers from the schedule boundaries", async () => {
    serve();
    await open();
    const table = await screen.findByRole("table", { name: /الإصدار 1/ });
    expect(within(table).getByRole("row", { name: /الشريحة 1/ })).toHaveTextContent("حتى 5 سنوات قيد");
    expect(within(table).getByRole("row", { name: /الشريحة 4/ })).toHaveTextContent("أكثر من 15 سنة قيد");
  });

  it("marks a used version as locked and offers no editing of it", async () => {
    serve();
    await open();
    await screen.findByRole("table", { name: /الإصدار 1/ });
    expect(screen.getByText("مقفل: مستخدم في طلبات مقدمة")).toBeInTheDocument();
    expect(screen.getByText("نشط")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: /الإصدار 1/ });
    expect(within(table).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(within(table).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("creates a new version after confirmation, prefilled from the shown schedule", async () => {
    const posts = serve();
    const { user } = await open();
    await screen.findByRole("table", { name: /الإصدار 1/ });

    await user.click(screen.getByRole("button", { name: "إنشاء إصدار جديد" }));
    const form = screen.getByRole("form", { name: "إنشاء إصدار جديد" });
    expect(within(form).getByRole("textbox", { name: "السنة المالية" })).toHaveValue("2026");
    const memberTier3 = within(form).getByRole("textbox", { name: "الشريحة 3 — العضو الأصلي" });
    expect(memberTier3).toHaveValue("750");
    await user.clear(memberTier3);
    await user.type(memberTier3, "٨٠٠");

    await user.click(within(form).getByRole("button", { name: "إنشاء الإصدار" }));
    const dialog = await screen.findByRole("dialog", { name: "تأكيد إنشاء إصدار جديد" });
    expect(dialog).toHaveTextContent("للسنة المالية 2026");
    expect(posts).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "إنشاء الإصدار" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    const body = posts[0] as { fiscal_year: number; tier_fees: Record<string, Record<string, number>>; admin_fee_with_beneficiaries: number };
    expect(body.fiscal_year).toBe(2026);
    expect(body.tier_fees["3"]).toEqual({ member: 800, spouse: 1000, child: 550, grad_son: 1500, parent: 1300 });
    expect(body.admin_fee_with_beneficiaries).toBe(175);
    expect(await screen.findByText("تم إنشاء الإصدار 2 للسنة المالية 2026.")).toBeInTheDocument();
  });

  it("refuses a non-numeric amount before asking for confirmation", async () => {
    const posts = serve();
    const { user } = await open();
    await screen.findByRole("table", { name: /الإصدار 1/ });
    await user.click(screen.getByRole("button", { name: "إنشاء إصدار جديد" }));
    const form = screen.getByRole("form", { name: "إنشاء إصدار جديد" });
    await user.clear(within(form).getByRole("textbox", { name: "الشريحة 1 — الأبناء" }));
    await user.click(within(form).getByRole("button", { name: "إنشاء الإصدار" }));
    expect(within(form).getAllByText("أدخل رقماً صحيحاً غير سالب").length).toBeGreaterThan(0);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
