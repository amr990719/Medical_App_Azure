import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { queryKeys } from "@/api/keys";
import { API, apiNotificationPreference, handlers } from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { server } from "@/test/server";
import { WhatsAppOptIn } from "./WhatsAppOptIn";

const CONSENT = "أوافق على استلام إشعارات طلبي عبر واتساب على الرقم:";

function serve(preference = apiNotificationPreference()) {
  const puts: unknown[] = [];
  server.use(
    handlers.whatsappOptIn(preference),
    http.put(`${API}/profile/notifications/`, async ({ request }) => {
      const body = (await request.json()) as { whatsapp_opt_in: boolean };
      puts.push(body);
      return HttpResponse.json({ ...preference, whatsapp_opt_in: body.whatsapp_opt_in });
    }),
  );
  return puts;
}

describe("WhatsAppOptIn", () => {
  it("shows the number the consent applies to, in an LTR element", async () => {
    serve();
    renderWithProviders(<WhatsAppOptIn />);
    expect(await screen.findByText("01012345678")).toHaveAttribute("dir", "ltr");
    expect(screen.getByRole("checkbox", { name: new RegExp(CONSENT) })).not.toBeChecked();
  });

  it("saves on change and shows the new state", async () => {
    const puts = serve();
    const { user } = renderWithProviders(<WhatsAppOptIn />);
    await user.click(await screen.findByRole("checkbox"));
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeChecked());
    expect(puts).toEqual([{ whatsapp_opt_in: true }]);
  });

  it("stays usable when the profile is frozen", async () => {
    // Consent is its own endpoint: nothing about the profile (PATCH is 409 under review) gates it.
    const puts = serve();
    const { user } = renderWithProviders(<WhatsAppOptIn />);
    const box = await screen.findByRole("checkbox");
    expect(box).toBeEnabled();
    await user.click(box);
    await waitFor(() => expect(puts).toHaveLength(1));
  });

  it("disables the box and explains when the mobile number is invalid", async () => {
    serve(apiNotificationPreference({ phone_number: "", phone_valid: false }));
    renderWithProviders(<WhatsAppOptIn />);
    expect(await screen.findByRole("checkbox")).toBeDisabled();
    expect(screen.getByText("يرجى إدخال رقم هاتف محمول صحيح أولًا.")).toBeInTheDocument();
  });

  it("renders nothing while WhatsApp is unavailable and the doctor is not opted in", async () => {
    serve(apiNotificationPreference({ whatsapp_available: false }));
    const { queryClient } = renderWithProviders(<WhatsAppOptIn />);
    await waitFor(() => expect(queryClient.isFetching()).toBe(0));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("still lets an opted-in doctor opt out while WhatsApp is unavailable", async () => {
    const puts = serve(apiNotificationPreference({ whatsapp_available: false, whatsapp_opt_in: true }));
    const { user } = renderWithProviders(<WhatsAppOptIn />);
    const box = await screen.findByRole("checkbox");
    expect(box).toBeChecked();
    expect(box).toBeEnabled();
    await user.click(box);
    await waitFor(() => expect(puts).toEqual([{ whatsapp_opt_in: false }]));
  });

  it("shows the server error when saving fails", async () => {
    server.use(
      handlers.whatsappOptIn(),
      http.put(`${API}/profile/notifications/`, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_ERROR",
              message: "x",
              fields: { whatsapp_opt_in: ["رقم الهاتف غير صالح للواتساب."] },
            },
          },
          { status: 400 },
        ),
      ),
    );
    const { user } = renderWithProviders(<WhatsAppOptIn />);
    await user.click(await screen.findByRole("checkbox"));
    expect(await screen.findByRole("alert")).toHaveTextContent("رقم الهاتف غير صالح للواتساب.");
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });

  it("refetches after a profile save, because a new phone clears consent", async () => {
    let current = apiNotificationPreference({ whatsapp_opt_in: true });
    server.use(http.get(`${API}/profile/notifications/`, () => HttpResponse.json(current)));
    const { queryClient } = renderWithProviders(<WhatsAppOptIn />);
    expect(await screen.findByRole("checkbox")).toBeChecked();
    current = apiNotificationPreference({ whatsapp_opt_in: false, phone_number: "01199999999" });
    await queryClient.invalidateQueries({ queryKey: queryKeys.whatsappOptIn });
    await waitFor(() => expect(screen.getByRole("checkbox")).not.toBeChecked());
    expect(screen.getByText("01199999999")).toBeInTheDocument();
  });
});
