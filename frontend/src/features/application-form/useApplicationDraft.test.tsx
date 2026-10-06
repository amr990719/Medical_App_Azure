import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { toCamel } from "@/api/case";
import { queryKeys } from "@/api/keys";
import {
  API,
  APP_ID,
  apiApplication,
  apiBeneficiary,
  apiDocument,
  apiProfile,
  apiReferenceData,
  draftHandlers,
  type ApiApplication,
} from "@/test/fixtures";
import { createTestQueryClient } from "@/test/render";
import { server } from "@/test/server";
import { useApplicationDraft } from "./useApplicationDraft";

const FAST = { debounceMs: 30, retryDelays: [10, 20, 40] };

function setup(app: ApiApplication = apiApplication(), profile = apiProfile()) {
  server.use(
    draftHandlers.application(app),
    draftHandlers.profile(profile),
    draftHandlers.fees(app.id),
    draftHandlers.validation(app.id),
  );
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(queryKeys.referenceData, toCamel(apiReferenceData));
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useApplicationDraft(app.id, FAST), { wrapper });
  return { ...view, queryClient };
}

async function ready(result: { current: ReturnType<typeof useApplicationDraft> }) {
  await waitFor(() => expect(result.current.state).not.toBeNull());
}

describe("useApplicationDraft", () => {
  it("autosave PATCHes once after the debounce, with only the changed field", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/profile/`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(apiProfile({ full_name: "أحمد محمد" }));
      }),
    );
    const { result } = setup();
    await ready(result);

    act(() => result.current.updateField("memberName", "أحمد"));
    act(() => result.current.updateField("memberName", "أحمد محمد"));
    expect(result.current.isDirty).toBe(true);

    await waitFor(() => expect(result.current.saveStatus).toBe("saved"));
    expect(bodies).toEqual([{ full_name: "أحمد محمد" }]);
    expect(result.current.isDirty).toBe(false);
  });

  it("routes application fields to PATCH /applications/{id}/", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/applications/${APP_ID}/`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(apiApplication({ work_status: "WORKING" }));
      }),
    );
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateField("workStatus", "WORKING"));
    await waitFor(() => expect(result.current.saveStatus).toBe("saved"));
    expect(bodies).toEqual([{ work_status: "WORKING" }]);
  });

  it("OCR merge fills only empty fields and keeps what the doctor typed", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { result } = setup(apiApplication(), apiProfile({ full_name: "اسم كتبه الطبيب" }));
    await ready(result);

    let filled = 0;
    act(() => {
      filled = result.current.applyOcrSuggestions({
        member_name: "أحمد محمد علي حسن",
        national_id: "28506150101234",
        address: "١٢ شارع عباس العقاد",
      });
    });
    expect(filled).toBe(2);
    expect(result.current.state?.memberName).toBe("اسم كتبه الطبيب");
    expect(result.current.state?.nationalId).toBe("28506150101234");
    expect(result.current.state?.address).toBe("١٢ شارع عباس العقاد");
  });

  it("fills birth year and gender from a complete national ID when they are empty", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateField("nationalId", "28506150101234"));
    expect(result.current.state?.birthYear).toBe("1985");
    expect(result.current.state?.gender).toBe("MALE");
  });

  it("flags a typed birth year that contradicts the national ID", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { result } = setup(apiApplication(), apiProfile({ birth_year: 1990 }));
    await ready(result);
    act(() => result.current.updateField("nationalId", "28506150101234"));
    expect(result.current.state?.birthYear).toBe("1990");
    expect(result.current.fieldErrors.birthYear).toBe("سنة الميلاد لا تطابق الرقم القومي");
  });

  it("kinship change clears that row's documents and PATCHes the new kinship", async () => {
    const wife = apiBeneficiary({
      documents: [apiDocument({ id: "d-m", document_type: "MARRIAGE_CERTIFICATE", beneficiary_id: "b-wife" })],
    });
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(apiBeneficiary({ kinship: "MOTHER", documents: [] }));
      }),
    );
    const { result } = setup(apiApplication({ beneficiaries: [wife] }));
    await ready(result);
    await waitFor(() => expect(result.current.rowServer(0)?.documents).toHaveLength(1));

    act(() => result.current.updateBeneficiary(0, "kinship", "MOTHER"));
    expect(result.current.rowServer(0)?.documents).toHaveLength(0);
    await waitFor(() => expect(result.current.saveStatus).toBe("saved"));
    expect(bodies).toEqual([{ kinship: "MOTHER" }]);
  });

  it("creates a beneficiary on the first edit of an empty row, then patches it", async () => {
    const posts: unknown[] = [];
    server.use(
      http.post(`${API}/applications/${APP_ID}/beneficiaries/`, async ({ request }) => {
        posts.push(await request.json());
        return HttpResponse.json(apiBeneficiary({ id: "b-new", row_number: 2, kinship: "WIFE", full_name: "" }), {
          status: 201,
        });
      }),
    );
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateBeneficiary(1, "kinship", "WIFE"));
    await waitFor(() => expect(result.current.saveStatus).toBe("saved"));
    expect(posts).toEqual([{ row_number: 2, kinship: "WIFE" }]);
    expect(result.current.state?.beneficiaries[1]?.id).toBe("b-new");
  });

  it("asks before deleting a cleared row and deletes it after confirmation", async () => {
    let deleted = false;
    server.use(
      http.patch(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, () => HttpResponse.json(apiBeneficiary())),
      http.delete(`${API}/applications/${APP_ID}/beneficiaries/b-wife/`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { result } = setup(apiApplication({ beneficiaries: [apiBeneficiary()] }));
    await ready(result);
    act(() => result.current.clearRow(0));
    expect(result.current.pendingDeletion).toBe(0);
    await act(() => result.current.confirmDeletion());
    expect(deleted).toBe(true);
    expect(result.current.pendingDeletion).toBeNull();
    expect(result.current.state?.beneficiaries[0]).toEqual({ kinship: "", name: "", birthYear: "", nationalId: "" });
  });

  it("restores a cleared row when deletion is cancelled", async () => {
    const { result } = setup(apiApplication({ beneficiaries: [apiBeneficiary()] }));
    await ready(result);
    act(() => result.current.clearRow(0));
    act(() => result.current.cancelDeletion());
    expect(result.current.state?.beneficiaries[0]?.name).toBe("منى سعيد عبد الله");
    expect(result.current.isDirty).toBe(false);
  });

  it("save error retries with backoff and recovers", async () => {
    let calls = 0;
    server.use(
      http.patch(`${API}/profile/`, () => {
        calls += 1;
        return calls < 3 ? HttpResponse.error() : HttpResponse.json(apiProfile({ address: "شارع" }));
      }),
    );
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateField("address", "شارع"));
    await waitFor(() => expect(result.current.saveStatus).toBe("saved"));
    expect(calls).toBe(3);
  });

  it("save error sets status error after the retries and keeps the typed value", async () => {
    let calls = 0;
    server.use(
      http.patch(`${API}/profile/`, () => {
        calls += 1;
        return HttpResponse.json({ error: { code: "SERVER_ERROR", message: "x", fields: {} } }, { status: 503 });
      }),
    );
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateField("address", "شارع"));
    await waitFor(() => expect(result.current.saveStatus).toBe("error"));
    expect(calls).toBe(4);
    expect(result.current.state?.address).toBe("شارع");
    expect(result.current.isDirty).toBe(true);
  });

  it("shows server field errors and still saves the other fields", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(`${API}/profile/`, async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        bodies.push(body);
        if ("national_id" in body) {
          return HttpResponse.json(
            {
              error: {
                code: "DUPLICATE_NATIONAL_ID",
                message: "الرقم القومي مسجل لعضو آخر",
                fields: { national_id: ["الرقم القومي مسجل لعضو آخر"] },
              },
            },
            { status: 409 },
          );
        }
        return HttpResponse.json(apiProfile({ address: "شارع" }));
      }),
    );
    const { result } = setup();
    await ready(result);
    act(() => {
      result.current.updateField("address", "شارع");
      result.current.updateField("nationalId", "28506150101234");
    });
    await waitFor(() => expect(result.current.fieldErrors.nationalId).toBe("الرقم القومي مسجل لعضو آخر"));
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual({ address: "شارع", birth_year: 1985, gender: "MALE" });
    expect(result.current.saveStatus).toBe("error");
  });

  it("is read-only when the application is SUBMITTED: no edits, no requests", async () => {
    const { result } = setup(apiApplication({ status: "SUBMITTED", is_editable: false }));
    await ready(result);
    expect(result.current.readOnly).toBe(true);
    act(() => result.current.updateField("memberName", "تغيير"));
    expect(result.current.state?.memberName).toBe("");
    expect(result.current.isDirty).toBe(false);
  });

  it("warns before unload while edits are unsaved", async () => {
    server.use(http.patch(`${API}/profile/`, () => HttpResponse.json(apiProfile())));
    const { result } = setup();
    await ready(result);
    act(() => result.current.updateField("nationalId", "2850615"));
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});
