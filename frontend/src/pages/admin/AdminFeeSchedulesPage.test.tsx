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
      const created = { ...fy2026, ...body, id: "new-version", version: 3, is_active: true, locked_at: null } as ApiFeeSchedule;
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
const amounts = (table: HTMLElement, tier: number) =>
  Array.from(tierRow(table, tier)).map((td) => td.textContent?.trim());

describe("AdminFeeSchedulesPage (PROMPT.md §17.1, §44)", () => {
  it("shows the active FY 2026 schedule with tier 0 and the exact amounts", async () => {
    serve();
    await open();
    const table = await screen.findByRole("table", { name: /السنة المالية 2026 — الإصدار 2/ });
    const headers = within(table).getAllByRole("columnheader").map((th) => th.textContent?.trim());
    expect(headers).toEqual(["الشريحة", "العضو الأصلي", "الزوج / الزوجة", "الأبناء", "ابن جامعي / خريج", "الوالدان"]);
    expect(amounts(table, 0)).toEqual(["400", "880", "550", "غير متاح", "1٬155"]);
    expect(amounts(table, 1)).toEqual(["660", "880", "550", "1٬320", "1٬155"]);
    expect(amounts(table, 2)).toEqual(["770", "1٬045", "605", "1٬540", "1٬320"]);
    expect(amounts(table, 3)).toEqual(["825", "1٬100", "605", "1٬650", "1٬430"]);
    expect(amounts(table, 4)).toEqual(["935", "1٬155", "660", "1٬925", "1٬540"]);
    expect(screen.getByText(/وليس اشتراكاً مجانياً/)).toBeInTheDocument();

    const settings = screen.getByRole("region", { name: "إعدادات الحساب" });
    expect(within(settings).getByText("طريقة الرسوم الإدارية").nextElementSibling).toHaveTextContent(
      "200 ج.م + 175 ج.م × عدد المستفيدين",
    );
    expect(within(settings).getByText("سن تطبيق السقف").nextElementSibling).toHaveTextContent("70");
    expect(within(settings).getByText("قيمة السقف").nextElementSibling).toHaveTextContent("500 ج.م");
  });

  it("labels the tiers from the schedule boundaries", async () => {
    serve();
    await open();
    const table = await screen.findByRole("table", { name: /الإصدار 2/ });
    expect(within(table).getByRole("row", { name: /الشريحة 0/ })).toHaveTextContent("سنة القيد هي سنة الاشتراك");
    expect(within(table).getByRole("row", { name: /الشريحة 1/ })).toHaveTextContent("من 1 إلى 5 سنة قيد");
    expect(within(table).getByRole("row", { name: /الشريحة 4/ })).toHaveTextContent("أكثر من 15 سنة قيد");
  });

  it("marks a used version as locked and offers no editing of it", async () => {
    serve();
    await open();
    await screen.findByRole("table", { name: /الإصدار 2/ });
    expect(screen.getByText("مقفل: مستخدم في طلبات مقدمة")).toBeInTheDocument();
    expect(screen.getAllByText("نشط").length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: /الإصدار 2/ });
    expect(within(table).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(within(table).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("creates a new version after confirmation, prefilled from the shown schedule", async () => {
    const posts = serve();
    const { user } = await open();
    await screen.findByRole("table", { name: /الإصدار 2/ });

    await user.click(screen.getByRole("button", { name: "إنشاء إصدار جديد" }));
    const form = screen.getByRole("form", { name: "إنشاء إصدار جديد" });
    expect(within(form).getByRole("textbox", { name: "السنة المالية" })).toHaveValue("2026");
    expect(within(form).getByRole("textbox", { name: "الشريحة 0 — العضو الأصلي" })).toHaveValue("400");
    const unavailable = within(form).getByRole("checkbox", { name: "غير متاح — الشريحة 0 — ابن جامعي / خريج" });
    expect(unavailable).toBeChecked();
    expect(within(form).getByRole("textbox", { name: "الشريحة 0 — ابن جامعي / خريج" })).toBeDisabled();
    expect(within(form).getByRole("textbox", { name: "رسوم إدارية ثابتة" })).toHaveValue("200");
    expect(within(form).getByRole("textbox", { name: "رسوم إدارية لكل مستفيد" })).toHaveValue("175");
    const memberTier3 = within(form).getByRole("textbox", { name: "الشريحة 3 — العضو الأصلي" });
    expect(memberTier3).toHaveValue("825");
    await user.clear(memberTier3);
    await user.type(memberTier3, "٩٠٠");

    await user.click(within(form).getByRole("button", { name: "إنشاء الإصدار" }));
    const dialog = await screen.findByRole("dialog", { name: "تأكيد إنشاء إصدار جديد" });
    expect(dialog).toHaveTextContent("للسنة المالية 2026");
    expect(posts).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "إنشاء الإصدار" }));

    await waitFor(() => expect(posts).toHaveLength(1));
    const body = posts[0] as {
      fiscal_year: number;
      tier_fees: Record<string, Record<string, number | null>>;
      admin_fee_base: number;
      admin_fee_per_beneficiary: number;
    };
    expect(body.fiscal_year).toBe(2026);
    expect(body.tier_fees["0"]).toEqual({ member: 400, spouse: 880, child: 550, grad_son: null, parent: 1155 });
    expect(body.tier_fees["3"]).toEqual({ member: 900, spouse: 1100, child: 605, grad_son: 1650, parent: 1430 });
    expect([body.admin_fee_base, body.admin_fee_per_beneficiary]).toEqual([200, 175]);
    expect(body).not.toHaveProperty("admin_fee_member_only");
    expect(body).not.toHaveProperty("admin_fee_formula");
    expect(await screen.findByText("تم إنشاء الإصدار 3 للسنة المالية 2026.")).toBeInTheDocument();
  });

  it("sends an amount for tier 0 graduates when it is made available", async () => {
    const posts = serve();
    const { user } = await open();
    await screen.findByRole("table", { name: /الإصدار 2/ });
    await user.click(screen.getByRole("button", { name: "إنشاء إصدار جديد" }));
    const form = screen.getByRole("form", { name: "إنشاء إصدار جديد" });
    await user.click(within(form).getByRole("checkbox", { name: "غير متاح — الشريحة 0 — ابن جامعي / خريج" }));
    const cell = within(form).getByRole("textbox", { name: "الشريحة 0 — ابن جامعي / خريج" });
    await user.type(cell, "1100");
    await user.click(within(form).getByRole("button", { name: "إنشاء الإصدار" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "إنشاء الإصدار" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect((posts[0] as { tier_fees: Record<string, Record<string, number | null>> }).tier_fees["0"]?.grad_son).toBe(1100);
  });

  it("refuses a non-numeric amount before asking for confirmation", async () => {
    const posts = serve();
    const { user } = await open();
    await screen.findByRole("table", { name: /الإصدار 2/ });
    await user.click(screen.getByRole("button", { name: "إنشاء إصدار جديد" }));
    const form = screen.getByRole("form", { name: "إنشاء إصدار جديد" });
    await user.clear(within(form).getByRole("textbox", { name: "الشريحة 1 — الأبناء" }));
    await user.click(within(form).getByRole("button", { name: "إنشاء الإصدار" }));
    expect(within(form).getAllByText("أدخل رقماً صحيحاً غير سالب").length).toBeGreaterThan(0);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
