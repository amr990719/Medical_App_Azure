import { act, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { SESSION_EXPIRED_EVENT } from "@/api/client";
import { queryKeys } from "@/api/keys";
import { API, apiApplication, handlers, meAdmin, meDoctor } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";
import { browser } from "@/utils/browser";

describe("route guards", () => {
  it("sends a signed-out visitor from /dashboard to the landing page", async () => {
    server.use(handlers.me(null), handlers.devUsersDisabled());
    const { router } = renderApp("/dashboard");
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(await screen.findByRole("link", { name: "تسجيل الدخول" })).toBeInTheDocument();
  });

  it("sends a doctor away from /admin/* to /dashboard", async () => {
    server.use(handlers.me(meDoctor), handlers.referenceData(), handlers.applications([]));
    const { router } = renderApp("/admin/applications");
    await waitFor(() => expect(router.state.location.pathname).toBe("/dashboard"));
  });

  it("sends an admin away from doctor pages to /admin/dashboard", async () => {
    server.use(handlers.me(meAdmin), handlers.referenceData());
    const { router } = renderApp("/dashboard");
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/dashboard"));
  });

  it("lets a doctor reach the dashboard", async () => {
    server.use(handlers.me(meDoctor), handlers.referenceData(), handlers.applications([]));
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "مرحباً د. أحمد" })).toBeInTheDocument();
  });

  it("returns to the landing page when the session expires", async () => {
    let signedIn = true;
    server.use(
      http.get(`${API}/auth/me/`, () =>
        signedIn
          ? HttpResponse.json(meDoctor)
          : HttpResponse.json(
              { error: { code: "NOT_AUTHENTICATED", message: "x", fields: {} } },
              { status: 401 },
            ),
      ),
      handlers.referenceData(),
      handlers.applications([]),
      handlers.devUsersDisabled(),
    );
    const { router } = renderApp("/dashboard");
    await screen.findByRole("heading", { name: "مرحباً د. أحمد" });
    signedIn = false;
    act(() => {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});

describe("sign-out", () => {
  it("posts logout, clears the query cache and shows the signed-out page", async () => {
    let loggedOut = false;
    server.use(
      handlers.me(meDoctor),
      handlers.referenceData(),
      handlers.applications([apiApplication()]),
      http.post(`${API}/auth/logout/`, () => {
        loggedOut = true;
        return HttpResponse.json({ entra_logout_url: null });
      }),
    );
    const { router, queryClient, user } = renderApp("/dashboard");
    await screen.findByRole("heading", { name: "مرحباً د. أحمد" });
    expect(queryClient.getQueryData(queryKeys.applications.list())).toBeDefined();

    await user.click(screen.getByRole("button", { name: "تسجيل الخروج" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/signed-out"));
    expect(loggedOut).toBe(true);
    expect(queryClient.getQueryData(queryKeys.applications.list())).toBeUndefined();
    expect(await screen.findByRole("heading", { name: "تم تسجيل الخروج" })).toBeInTheDocument();
  });

  it("continues to the Entra logout page when the server returns one", async () => {
    const assign = vi.spyOn(browser, "assign").mockImplementation(() => {});
    server.use(
      handlers.me(meDoctor),
      handlers.referenceData(),
      handlers.applications([]),
      http.post(`${API}/auth/logout/`, () =>
        HttpResponse.json({ entra_logout_url: "https://login.example/logout" }),
      ),
    );
    const { user } = renderApp("/dashboard");
    await screen.findByRole("heading", { name: "مرحباً د. أحمد" });
    await user.click(screen.getByRole("button", { name: "تسجيل الخروج" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://login.example/logout"));
  });
});
