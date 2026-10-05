import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, handlers, meDoctor } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const LOGIN = "/api/v1/auth/login/?next=%2Fdashboard";

describe("LandingPage", () => {
  it("offers sign-in and account creation through Entra External ID", async () => {
    server.use(handlers.me(null), handlers.devUsersDisabled());
    renderApp("/");
    expect(await screen.findByRole("link", { name: "تسجيل الدخول" })).toHaveAttribute("href", LOGIN);
    expect(screen.getByRole("link", { name: "إنشاء حساب" })).toHaveAttribute("href", LOGIN);
    expect(screen.queryByRole("textbox", { name: /كلمة المرور/ })).toBeNull();
  });

  it("explains an Entra callback error", async () => {
    server.use(handlers.me(null), handlers.devUsersDisabled());
    renderApp("/?auth_error=MFA_REQUIRED");
    expect(await screen.findByRole("alert")).toHaveTextContent("حسابات المسؤولين تتطلب التحقق بخطوتين.");
  });

  it("falls back to a generic message for unknown error codes", async () => {
    server.use(handlers.me(null), handlers.devUsersDisabled());
    renderApp("/?auth_error=<script>");
    expect(await screen.findByRole("alert")).toHaveTextContent("تعذّر تسجيل الدخول. يرجى المحاولة مرة أخرى.");
  });

  it("sends a signed-in doctor to the dashboard", async () => {
    server.use(handlers.me(meDoctor), handlers.referenceData(), handlers.applications([]));
    const { router } = renderApp("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/dashboard"));
  });

  it("hides the dev login when the backend has it disabled", async () => {
    server.use(handlers.me(null), handlers.devUsersDisabled());
    renderApp("/");
    await screen.findByRole("link", { name: "تسجيل الدخول" });
    expect(screen.queryByText("دخول تجريبي (بيئة التطوير فقط)")).toBeNull();
  });

  it("dev login signs in as a seeded user and opens the dashboard", async () => {
    let signedIn = false;
    let csrf: string | null = null;
    document.cookie = "csrftoken=dev-csrf; path=/";
    server.use(
      http.get(`${API}/auth/me/`, () =>
        signedIn
          ? HttpResponse.json(meDoctor)
          : HttpResponse.json({ error: { code: "NOT_AUTHENTICATED", message: "x", fields: {} } }, { status: 401 }),
      ),
      http.get(`${API}/auth/dev/users/`, () =>
        HttpResponse.json([
          { id: "1", email: "doctor@dev.local", role: "DOCTOR", display_name: "أحمد محمد علي حسن" },
          { id: "2", email: "admin@dev.local", role: "ADMIN", display_name: "مسؤول المراجعة" },
        ]),
      ),
      http.post(`${API}/auth/dev/login/`, async ({ request }) => {
        csrf = request.headers.get("X-CSRFToken");
        expect(await request.json()).toEqual({ email: "doctor@dev.local" });
        signedIn = true;
        return HttpResponse.json(meDoctor);
      }),
      handlers.referenceData(),
      handlers.applications([]),
    );
    const { router, user } = renderApp("/");
    await user.click(await screen.findByRole("button", { name: /الدخول باسم أحمد محمد علي حسن/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/dashboard"));
    expect(csrf).toBe("dev-csrf");
  });
});
