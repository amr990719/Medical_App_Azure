import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { server } from "@/test/server";
import { ApiError, apiFetch, apiUpload, SESSION_EXPIRED_EVENT } from "./client";

const url = (path: string) => `http://localhost:3000/api/v1${path}`;

async function failure(request: Promise<unknown>): Promise<ApiError> {
  try {
    await request;
  } catch (error) {
    return error as ApiError;
  }
  throw new Error("expected the request to fail");
}

function setCsrfCookie(value: string) {
  document.cookie = `csrftoken=${value}; path=/`;
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("prefixes /api/v1 and parses JSON", async () => {
    server.use(http.get(url("/reference-data/"), () => HttpResponse.json({ fiscal_year: 2026 })));
    await expect(apiFetch<{ fiscal_year: number }>("/reference-data/")).resolves.toEqual({
      fiscal_year: 2026,
    });
  });

  it("serializes query parameters and skips empty ones", async () => {
    let seen = "";
    server.use(
      http.get(url("/applications/"), ({ request }) => {
        seen = new URL(request.url).search;
        return HttpResponse.json({ results: [] });
      }),
    );
    await apiFetch("/applications/", { query: { page: 2, search: "", status: undefined } });
    expect(seen).toBe("?page=2");
  });

  it("sends the csrf header on POST", async () => {
    setCsrfCookie("tok123");
    let header: string | null = null;
    let body: unknown = null;
    server.use(
      http.post(url("/applications/"), async ({ request }) => {
        header = request.headers.get("X-CSRFToken");
        body = await request.json();
        return HttpResponse.json({ id: "a1" }, { status: 201 });
      }),
    );
    await apiFetch("/applications/", { method: "POST", body: { application_type: "FIRST_TIME" } });
    expect(header).toBe("tok123");
    expect(body).toEqual({ application_type: "FIRST_TIME" });
  });

  it("does not send the csrf header on GET", async () => {
    setCsrfCookie("tok123");
    let header: string | null = "unset";
    server.use(
      http.get(url("/profile/"), ({ request }) => {
        header = request.headers.get("X-CSRFToken");
        return HttpResponse.json({});
      }),
    );
    await apiFetch("/profile/");
    expect(header).toBeNull();
  });

  it("parses the error envelope into ApiError", async () => {
    server.use(
      http.patch(url("/profile/"), () =>
        HttpResponse.json(
          {
            error: {
              code: "DUPLICATE_NATIONAL_ID",
              message: "الرقم القومي مسجل لعضو آخر",
              fields: { national_id: ["الرقم القومي مسجل لعضو آخر"] },
            },
          },
          { status: 409 },
        ),
      ),
    );
    const error = await failure(apiFetch("/profile/", { method: "PATCH", body: {} }));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "DUPLICATE_NATIONAL_ID",
      message: "الرقم القومي مسجل لعضو آخر",
      fields: { national_id: ["الرقم القومي مسجل لعضو آخر"] },
    });
  });

  it("keeps submission errors with their wizard steps", async () => {
    const errors = [{ step: 1, field: "member.phone_number", code: "INVALID", message: "خطأ" }];
    server.use(
      http.post(url("/applications/a1/submit/"), () =>
        HttpResponse.json(
          { error: { code: "VALIDATION_ERROR", message: "يرجى التصحيح", fields: {}, errors } },
          { status: 400 },
        ),
      ),
    );
    const error = await failure(apiFetch("/applications/a1/submit/", { method: "POST" }));
    expect(error.errors).toEqual(errors);
  });

  it("turns a non-JSON failure into a generic Arabic error, never raw text", async () => {
    server.use(
      http.get(url("/profile/"), () => new HttpResponse("<html>Traceback…</html>", { status: 502 })),
    );
    const error = await failure(apiFetch("/profile/"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("SERVER_ERROR");
    expect(error.message).not.toContain("Traceback");
    expect(error.message).toMatch(/[؀-ۿ]/);
  });

  it("turns a network failure into NETWORK_ERROR", async () => {
    server.use(http.get(url("/profile/"), () => HttpResponse.error()));
    const error = await failure(apiFetch("/profile/"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("NETWORK_ERROR");
    expect(error.status).toBe(0);
  });

  it("returns undefined for 204", async () => {
    server.use(
      http.delete(url("/documents/d1/"), () => new HttpResponse(null, { status: 204 })),
    );
    await expect(apiFetch("/documents/d1/", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("emits session:expired on 401", async () => {
    server.use(
      http.get(url("/profile/"), () =>
        HttpResponse.json(
          { error: { code: "NOT_AUTHENTICATED", message: "يرجى تسجيل الدخول", fields: {} } },
          { status: 401 },
        ),
      ),
    );
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    await apiFetch("/profile/").catch(() => undefined);
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("does not emit session:expired when the caller expects a 401", async () => {
    server.use(
      http.get(url("/auth/me/"), () =>
        HttpResponse.json(
          { error: { code: "NOT_AUTHENTICATED", message: "x", fields: {} } },
          { status: 401 },
        ),
      ),
    );
    const listener = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, listener);
    await apiFetch("/auth/me/", { unauthorized: "ignore" }).catch(() => undefined);
    window.removeEventListener(SESSION_EXPIRED_EVENT, listener);
    expect(listener).not.toHaveBeenCalled();
  });

  it("sends multipart without forcing a content type", async () => {
    setCsrfCookie("tok123");
    let contentType: string | null = null;
    server.use(
      http.post(url("/applications/a1/documents/"), ({ request }) => {
        contentType = request.headers.get("Content-Type");
        return HttpResponse.json({ id: "d1" }, { status: 201 });
      }),
    );
    const form = new FormData();
    form.append("document_type", "NATIONAL_ID_FRONT");
    await apiFetch("/applications/a1/documents/", { method: "POST", body: form });
    expect(contentType).toMatch(/^multipart\/form-data; boundary=/);
  });
});

describe("apiUpload", () => {
  it("uploads multipart with the csrf header and reports progress", async () => {
    setCsrfCookie("tok456");
    let header: string | null = null;
    server.use(
      http.post(url("/applications/a1/documents/"), ({ request }) => {
        header = request.headers.get("X-CSRFToken");
        return HttpResponse.json({ id: "d1", original_filename: "front.png" }, { status: 201 });
      }),
    );
    const form = new FormData();
    form.append("file", new File(["x"], "front.png", { type: "image/png" }));
    const progress = vi.fn();
    const result = await apiUpload<{ id: string }>("/applications/a1/documents/", form, progress);
    expect(result.id).toBe("d1");
    expect(header).toBe("tok456");
    expect(progress).toHaveBeenLastCalledWith(100);
  });

  it("parses the error envelope of a refused upload", async () => {
    server.use(
      http.post(url("/applications/a1/documents/"), () =>
        HttpResponse.json(
          { error: { code: "FILE_TOO_LARGE", message: "حجم الملف كبير", fields: {} } },
          { status: 413 },
        ),
      ),
    );
    const error = await failure(apiUpload("/applications/a1/documents/", new FormData()));
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 413, code: "FILE_TOO_LARGE" });
  });
});

describe("path safety (route params are interpolated into API paths)", () => {
  // React Router decodes %2F in params, so a crafted link can put "../" into an id.
  const unsafe = [
    "/admin/applications/../../auth/logout/transition/",
    "/admin/applications/./x/",
    "/documents/x/..%2F..%2Fauth%2Flogout/",
    "/applications/x?y=1/submit/",
    "/applications/x#/submit/",
    String.raw`/applications/x\..\..\auth/`,
  ];

  it.each(unsafe)("refuses %s without sending a request", async (path) => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    await expect(apiFetch(path, { method: "POST" })).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("refuses an unsafe upload path", async () => {
    await expect(apiUpload("/applications/../../auth/logout/documents/", new FormData())).rejects.toMatchObject({
      code: "NOT_FOUND",
    });
  });

  it("still sends normal paths", async () => {
    server.use(http.get(`${window.location.origin}/api/v1/applications/5f0c1a52-0000-4000-8000-000000000123/`, () => HttpResponse.json({ ok: true })));
    await expect(apiFetch("/applications/5f0c1a52-0000-4000-8000-000000000123/")).resolves.toEqual({ ok: true });
  });
});
