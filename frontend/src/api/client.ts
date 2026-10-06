/**
 * Fetch wrapper for the Django API (same-origin `/api/v1`, session cookie, PROMPT.md §46 errors).
 * - Unsafe methods send `X-CSRFToken` from the `csrftoken` cookie set by GET /auth/me/.
 * - Every failure becomes an `ApiError` with an Arabic message; raw bodies never reach the UI.
 * - A 401 dispatches `session:expired` so the session hook can refetch /auth/me/ and the guards
 *   send the user to the landing page.
 */
import { ar } from "@/i18n/ar";

export const API_PREFIX = "/api/v1";
export const SESSION_EXPIRED_EVENT = "session:expired";

export type ApiFieldErrors = Record<string, string[]>;

export interface ApiStepError {
  step: number;
  field: string;
  code: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: ApiFieldErrors;
  readonly errors: ApiStepError[] | undefined;

  constructor(
    status: number,
    code: string,
    message: string,
    fields: ApiFieldErrors = {},
    errors?: ApiStepError[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.errors = errors;
  }
}

type QueryValue = string | number | boolean | null | undefined;
type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export interface ApiRequestInit {
  method?: Method;
  body?: unknown;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** "ignore" for calls where 401 is an expected answer (GET /auth/me/ when signed out). */
  unauthorized?: "event" | "ignore";
}

const SAFE_METHODS = new Set<Method>(["GET"]);

export function readCookie(name: string): string | undefined {
  for (const part of document.cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return undefined;
}

// Every API path segment is a literal name or a UUID. Ids come from route params, which React
// Router decodes (%2F → "/"), so a crafted link could otherwise smuggle "../", "?" or "#" into a
// path and send a CSRF-bearing request to another same-origin endpoint.
const SAFE_SEGMENT = /^[A-Za-z0-9_-]*$/;

function assertSafePath(path: string): void {
  if (!path.startsWith("/") || !path.split("/").every((segment) => SAFE_SEGMENT.test(segment))) {
    throw new ApiError(404, "NOT_FOUND", ar.errors.notFound);
  }
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  assertSafePath(path);
  // Absolute URL so the same code works in the browser and in Node-based tests.
  const url = new URL(`${API_PREFIX}${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

function fallbackMessage(status: number): string {
  return status === 401 ? ar.errors.sessionExpired : ar.errors.unexpected;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Build an ApiError from a parsed §46 envelope (or anything else the server answered). */
export function toApiError(status: number, payload: unknown): ApiError {
  const envelope = isRecord(payload) && isRecord(payload.error) ? payload.error : undefined;
  if (envelope && typeof envelope.code === "string" && typeof envelope.message === "string") {
    const fields = isRecord(envelope.fields) ? (envelope.fields as ApiFieldErrors) : {};
    const errors = Array.isArray(envelope.errors) ? (envelope.errors as ApiStepError[]) : undefined;
    return new ApiError(status, envelope.code, envelope.message, fields, errors);
  }
  const code = status === 401 ? "NOT_AUTHENTICATED" : status >= 500 ? "SERVER_ERROR" : "HTTP_ERROR";
  return new ApiError(status, code, fallbackMessage(status));
}

function notifyUnauthorized(status: number, mode: ApiRequestInit["unauthorized"]) {
  if (status === 401 && mode !== "ignore") {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
}

function parseJson(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const method = init.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  let body: BodyInit | undefined;

  if (init.body instanceof FormData) {
    body = init.body; // the browser sets multipart/form-data with its boundary
  } else if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.body);
  }
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie("csrftoken");
    if (token) headers.set("X-CSRFToken", token);
  }

  const url = buildUrl(path, init.query);
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body,
      credentials: "same-origin",
      signal: init.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "NETWORK_ERROR", ar.errors.network);
  }

  const payload = parseJson(await response.text());
  if (!response.ok) {
    notifyUnauthorized(response.status, init.unauthorized);
    throw toApiError(response.status, payload);
  }
  return payload as T;
}

/**
 * Multipart upload through XMLHttpRequest, the only browser API that reports upload progress.
 * `onProgress` receives 0–100.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  onProgress?: (percent: number) => void,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", buildUrl(path));
    xhr.setRequestHeader("Accept", "application/json");
    const token = readCookie("csrftoken");
    if (token) xhr.setRequestHeader("X-CSRFToken", token);

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    xhr.addEventListener("load", () => {
      const payload = parseJson(xhr.responseText);
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve(payload as T);
        return;
      }
      notifyUnauthorized(xhr.status, "event");
      reject(toApiError(xhr.status, payload));
    });
    xhr.addEventListener("error", () => reject(new ApiError(0, "NETWORK_ERROR", ar.errors.network)));
    xhr.addEventListener("abort", () => reject(new DOMException("Upload aborted", "AbortError")));
    xhr.send(form);
  });
}
