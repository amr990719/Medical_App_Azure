import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API, apiProfile, draftHandlers, handlers, meDoctor } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { server } from "@/test/server";

const completed = apiProfile({
  full_name: "أحمد محمد علي حسن",
  national_id: "28506150101234",
  syndicate_type: "HUMAN_MEDICINE",
  sub_syndicate: "القاهرة",
  syndicate_registration_number: "12345",
  syndicate_registration_year: 2014,
  phone_number: "01012345678",
  governorate: "القاهرة",
  neighborhood: "مدينة نصر",
  address: "شارع عباس العقاد",
});

function setup(profile = completed) {
  const patches: unknown[] = [];
  server.use(
    handlers.me(meDoctor),
    handlers.referenceData(),
    draftHandlers.profile(profile),
    http.patch(`${API}/profile/`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      patches.push(body);
      return HttpResponse.json({ ...profile, ...body });
    }),
  );
  return { ...renderApp("/profile"), patches };
}

describe("ProfilePage", () => {
  it("shows the identity data read-only and the contact data in the form", async () => {
    setup();
    expect(await screen.findByRole("heading", { level: 1, name: "الملف الشخصي" })).toBeInTheDocument();
    expect(await screen.findByText("أحمد محمد علي حسن")).toBeInTheDocument();
    expect(screen.getByText("doctor@dev.local")).toBeInTheDocument();
    expect(screen.getByText("28506150101234")).toHaveAttribute("dir", "ltr");
    expect(screen.getByText("بشري")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "تعديلها من استمارة الاشتراك" })).toHaveAttribute(
      "href",
      "/application/new",
    );

    expect(screen.getByLabelText("الهاتف المحمول")).toHaveValue("01012345678");
    expect(screen.getByLabelText("المحافظة")).toHaveValue("القاهرة");
    expect(screen.getByLabelText("الحي / المركز")).toHaveValue("مدينة نصر");
    expect(screen.getByLabelText("العنوان")).toHaveValue("شارع عباس العقاد");
    expect(screen.getByRole("button", { name: "حفظ التعديلات" })).toBeDisabled();
  });

  it("marks missing identity data instead of leaving blanks", async () => {
    setup(apiProfile());
    expect(await screen.findAllByText("لم يُدخل بعد")).not.toHaveLength(0);
  });

  it("saves only the changed fields, normalizing Arabic digits", async () => {
    const { user, patches } = setup();
    const phone = await screen.findByLabelText("الهاتف المحمول");
    await user.clear(phone);
    await user.type(phone, "٠١١٢٣٤٥٦٧٨٩");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));

    expect(await screen.findByRole("status")).toHaveTextContent("تم حفظ التعديلات.");
    expect(patches).toEqual([{ phone_number: "01123456789" }]);
    expect(screen.getByRole("button", { name: "حفظ التعديلات" })).toBeDisabled();
  });

  it("shows the instant validation message and sends nothing for an invalid mobile", async () => {
    const { user, patches } = setup();
    const phone = await screen.findByLabelText("الهاتف المحمول");
    await user.clear(phone);
    await user.type(phone, "0123");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));

    expect(await screen.findByText("رقم الهاتف المحمول غير صحيح")).toBeInTheDocument();
    expect(phone).toHaveAttribute("aria-invalid", "true");
    expect(patches).toEqual([]);
  });

  it("shows the server's field errors on the matching field", async () => {
    const { user } = setup();
    server.use(
      http.patch(`${API}/profile/`, () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_ERROR", message: "بيانات غير صحيحة", fields: { address: ["العنوان مرفوض"] } } },
          { status: 400 },
        ),
      ),
    );
    const address = await screen.findByLabelText("العنوان");
    await user.type(address, " ٣");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));

    expect(await screen.findByText("العنوان مرفوض")).toBeInTheDocument();
    expect(address).toHaveAttribute("aria-invalid", "true");
  });

  it("explains a locked profile (submitted application) with the server message", async () => {
    const { user } = setup();
    server.use(
      http.patch(`${API}/profile/`, () =>
        HttpResponse.json(
          { error: { code: "APPLICATION_NOT_EDITABLE", message: "لا يمكن تعديل الطلب في حالته الحالية", fields: {} } },
          { status: 409 },
        ),
      ),
    );
    await user.type(await screen.findByLabelText("الحي / المركز"), " أول");
    await user.click(screen.getByRole("button", { name: "حفظ التعديلات" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("لا يمكن تعديل الطلب في حالته الحالية");
  });

  it("offers a retry when the profile cannot be loaded", async () => {
    server.use(
      handlers.me(meDoctor),
      handlers.referenceData(),
      http.get(`${API}/profile/`, () =>
        HttpResponse.json({ error: { code: "SERVER_ERROR", message: "خطأ", fields: {} } }, { status: 500 }),
      ),
    );
    renderApp("/profile");
    await waitFor(() => expect(screen.getByRole("button", { name: "إعادة المحاولة" })).toBeInTheDocument());
  });
});
