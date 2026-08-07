/**
 * Typed HTTP client for the SOT Analyzer API.
 *
 * Server components run inside the Docker network and must use the internal
 * hostname; browser code must use the publicly reachable one. Picking the wrong
 * base URL is the classic Next.js + Docker failure, so it is resolved in one
 * place here rather than at each call site.
 */

const BROWSER_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const SERVER_BASE_URL =
  process.env.INTERNAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export function apiBaseUrl(): string {
  return typeof window === "undefined" ? SERVER_BASE_URL : BROWSER_BASE_URL;
}

/** Error envelope returned by `app.api.errors`. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const candidate = (value as { error?: unknown }).error;
  return typeof candidate === "object" && candidate !== null && "code" in candidate;
}

export interface RequestOptions {
  /** Query parameters. `undefined` and `null` entries are dropped. */
  params?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
  /** Next.js fetch cache revalidation, in seconds. */
  revalidate?: number;
}

export function buildQueryString(
  params: Record<string, string | number | boolean | undefined | null> = {},
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

/** Perform a GET request and parse the typed JSON response. */
export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${apiBaseUrl()}${path}${buildQueryString(options.params)}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: options.signal ?? null,
      ...(options.revalidate !== undefined ? { next: { revalidate: options.revalidate } } : {}),
    });
  } catch (cause) {
    // Network-level failure: the API is unreachable, not returning an error.
    throw new ApiError(0, "network_error", `Could not reach the API at ${apiBaseUrl()}.`, {
      cause: String(cause),
    });
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    if (isApiErrorBody(payload)) {
      throw new ApiError(
        response.status,
        payload.error.code,
        payload.error.message,
        payload.error.details ?? {},
      );
    }
    throw new ApiError(response.status, "http_error", `Request failed with ${response.status}.`);
  }

  return payload as T;
}
