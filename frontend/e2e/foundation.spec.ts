import { expect, test, type Page } from "@playwright/test";

/** The dev-login button of one seeded user, matched by its exact e-mail. */
const devLoginButton = (page: Page, email: string) =>
  page.getByRole("button").filter({ has: page.getByText(email, { exact: true }) });

/**
 * Session 4 smoke test: RTL shell, dev login through the Vite proxy, dashboard with real data.
 * Needs the development backend (`seed_dev_data` users) behind the proxy.
 */
test("landing page is Arabic RTL with Cairo and offers Entra sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByRole("link", { name: "تسجيل الدخول" })).toHaveAttribute(
    "href",
    "/api/v1/auth/login/?next=%2Fdashboard",
  );
  const font = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(font).toContain("Cairo");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("dev login opens the doctor dashboard with data from the API", async ({ page }) => {
  await page.goto("/");
  await devLoginButton(page, "doctor@dev.local").click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^مرحباً د\. /);
  await expect(page.getByRole("heading", { name: "طلباتي" })).toBeVisible();
  // Either the empty state or at least one application card rendered from GET /applications/.
  await expect(page.getByRole("article").or(page.getByText("لم تقدم أي طلبات بعد")).first()).toBeVisible();

  await page.getByRole("button", { name: "تسجيل الخروج" }).click();
  await expect(page).toHaveURL(/\/signed-out$/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/$/);
});

test("a doctor cannot open admin pages", async ({ page }) => {
  await page.goto("/");
  await devLoginButton(page, "doctor@dev.local").click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/admin/applications");
  await expect(page).toHaveURL(/\/dashboard$/);
});
