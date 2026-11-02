import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { API, apiNotificationPreference, handlers } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { WhatsAppPrompt } from "./WhatsAppPrompt";

const MESSAGE = "فعّل إشعارات واتساب لمتابعة طلبك أولًا بأول.";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("WhatsAppPrompt", () => {
  it("shows for a doctor not opted in, with a link to /profile", async () => {
    server.use(handlers.whatsappOptIn());
    renderWithProviders(<WhatsAppPrompt />);
    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تفعيل" })).toHaveAttribute("href", "/profile");
  });

  it("does not show for a doctor already opted in", async () => {
    server.use(handlers.whatsappOptIn(apiNotificationPreference({ whatsapp_opt_in: true })));
    const { queryClient } = renderWithProviders(<WhatsAppPrompt />);
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it("does not flash while loading", () => {
    server.use(handlers.whatsappOptIn());
    renderWithProviders(<WhatsAppPrompt />);
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it("does not render when the query errors", async () => {
    server.use(http.get(`${API}/profile/notifications/`, () => HttpResponse.json({}, { status: 500 })));
    const { queryClient } = renderWithProviders(<WhatsAppPrompt />);
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it("hides after dismissal and stays hidden on the next render", async () => {
    server.use(handlers.whatsappOptIn());
    const first = renderWithProviders(<WhatsAppPrompt />);
    await first.user.click(await screen.findByRole("button", { name: "إخفاء" }));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
    first.unmount();
    const second = renderWithProviders(<WhatsAppPrompt />);
    await waitFor(() => expect(second.queryClient.isFetching()).toBe(0));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });

  it("uses a storage key containing the doctor ID, so another doctor still sees it", async () => {
    server.use(handlers.whatsappOptIn(apiNotificationPreference({ doctor_id: "doctor-a" })));
    const first = renderWithProviders(<WhatsAppPrompt />);
    await first.user.click(await screen.findByRole("button", { name: "إخفاء" }));
    expect(localStorage.getItem("whatsapp-prompt-dismissed:doctor-a")).not.toBeNull();
    first.unmount();

    server.use(handlers.whatsappOptIn(apiNotificationPreference({ doctor_id: "doctor-b" })));
    renderWithProviders(<WhatsAppPrompt />);
    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
  });

  it("still renders when localStorage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    server.use(handlers.whatsappOptIn());
    const { user } = renderWithProviders(<WhatsAppPrompt />);
    expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "إخفاء" }));
    expect(screen.queryByText(MESSAGE)).not.toBeInTheDocument();
  });
});
