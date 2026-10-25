import type {
  BulkDeleteResponse,
  CookiesStatus,
  JobInfo,
  Library,
  LibraryDetails,
  LibraryIn,
  PaginatedPosts,
  ProfileInfo,
  QueryIn,
  QueryResponse,
  SourceItem,
} from "./api-types";

/**
 * Base URL for the FastAPI backend.
 *
 * - In development we default to `/api` and let the Vite dev server proxy it to
 *   the backend (see `vite.config.ts`). This keeps the browser same-origin, so
 *   there is no CORS/preflight involved at all.
 * - In production, either serve the SPA behind the same origin that exposes
 *   `/api`, or set `VITE_API_URL` at build time to the backend origin
 *   (e.g. `https://api.example.com`).
 *
 * Anything prefixed with `VITE_` is public: never put secrets here.
 */
const configuredBaseUrl = (import.meta.env.VITE_API_URL ?? "/api").trim();
export const API_BASE_URL = (configuredBaseUrl || "/api").replace(/\/+$/, "");

/** Identity header used by the backend (`X-User-Id`). */
export const USER_ID =
  (import.meta.env.VITE_USER_ID ?? "default").trim() || "default";

/** Optional `X-API-Key`; required only when `CRAG_API_KEY` is set on the backend. */
const API_KEY = (import.meta.env.VITE_API_KEY ?? "").trim();
let accessToken = "";

export function setAccessToken(token: string) {
  accessToken = token;
}

const DEFAULT_TIMEOUT_MS = 30_000;
const QUERY_TIMEOUT_MS = 180_000;

type ApiErrorKind = "network" | "timeout" | "http";

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  readonly detail: unknown;

  constructor(
    message: string,
    status: number,
    kind: ApiErrorKind,
    detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.kind = kind;
    this.detail = detail;
  }

  get isOffline(): boolean {
    return this.kind === "network" || this.kind === "timeout";
  }
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

export interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** Normalize FastAPI error payloads (`detail` can be a string, object or array). */
function extractErrorMessage(payload: unknown): string | null {
  if (!payload) return null;
  if (typeof payload === "string") return payload.trim() || null;

  if (Array.isArray(payload)) {
    const parts = payload
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const item = entry as Record<string, unknown>;
          const location = Array.isArray(item.loc)
            ? item.loc.slice(1).join(".")
            : "";
          const message = typeof item.msg === "string" ? item.msg : "";
          if (message) return location ? `${location}: ${message}` : message;
        }
        return null;
      })
      .filter((entry): entry is string => Boolean(entry));
    return parts.length > 0 ? parts.join(". ") : null;
  }

  if (typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if ("detail" in record) return extractErrorMessage(record.detail);
    if (typeof record.message === "string") return record.message;
    if (typeof record.error === "string") return record.error;
  }

  return null;
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  requestOptions: RequestOptions = {},
): Promise<T> {
  const { signal, timeoutMs = DEFAULT_TIMEOUT_MS } = requestOptions;

  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (import.meta.env.VITE_APP_MODE !== "query") {
    if (USER_ID) headers.set("X-User-Id", USER_ID);
    if (API_KEY) headers.set("X-API-Key", API_KEY);
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  signal?.addEventListener("abort", forwardAbort, { once: true });
  if (signal?.aborted) controller.abort();

  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  let response: Response;
  let payload: unknown;
  try {
    response = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });
    payload = await parseBody(response);
  } catch (error) {
    if (isAbortError(error)) {
      // Caller-driven abort: let the caller ignore it.
      if (signal?.aborted) throw error;
      if (timedOut) {
        throw new ApiError(
          "El backend tardó demasiado en responder. Inténtalo de nuevo.",
          0,
          "timeout",
        );
      }
    }
    throw new ApiError(
      "No se pudo conectar con el backend. Comprueba que el servidor esté en marcha.",
      0,
      "network",
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", forwardAbort);
  }

  if (!response.ok) {
    const message =
      extractErrorMessage(payload) ??
      `Error ${response.status} al llamar a ${endpoint}.`;
    throw new ApiError(message, response.status, "http", payload);
  }

  return payload as T;
}

type Params = Record<string, string | number | boolean | undefined | null>;

function toQueryString(params?: Params): string {
  if (!params) return "";
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    searchParams.set(key, String(value));
  }
  const qs = searchParams.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  getLibraries: (options?: RequestOptions) =>
    fetchApi<Library[]>("/libraries", {}, options),
  getLibrary: (libraryId: string, options?: RequestOptions) =>
    fetchApi<LibraryDetails>(
      `/libraries/${encodeURIComponent(libraryId)}`,
      {},
      options,
    ),
  getProfiles: (options?: RequestOptions) =>
    fetchApi<ProfileInfo[]>("/profiles", {}, options),
  updateLibrary: (libraryId: string, name: string, description = "") =>
    fetchApi<Library>(`/libraries/${encodeURIComponent(libraryId)}`, {
      method: "PATCH",
      body: JSON.stringify({ name, description }),
    }),
  deleteLibrary: (libraryId: string) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(libraryId)}`,
      { method: "DELETE" },
    ),
  deleteProfileFromLibrary: (libraryId: string, username: string) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(libraryId)}/profiles/${encodeURIComponent(username)}`,
      { method: "DELETE" },
    ),
  createLibrary: (data: LibraryIn) =>
    fetchApi<Library>("/libraries", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  addSource: (
    librarySlug: string,
    url: string,
    options?: Record<string, unknown>,
  ) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(librarySlug)}/sources`,
      {
        method: "POST",
        body: JSON.stringify({ url, ...options }),
      },
    ),
  linkProfile: (librarySlug: string, username: string) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(librarySlug)}/profiles/${encodeURIComponent(username)}/link`,
      { method: "POST" },
    ),
  addProfile: async (
    librarySlug: string,
    username: string,
    options?: Record<string, unknown>,
  ) => {
    await fetchApi<ProfileInfo>("/profiles", {
      method: "POST",
      body: JSON.stringify({
        username,
        max_posts: options?.max_posts || 50,
        interests: options?.interests || "",
        analysis_mode: options?.analysis_mode || "gemini",
      }),
    });
    return fetchApi<{ id: string; kind: string }>("/jobs/run", {
      method: "POST",
      body: JSON.stringify({
        username,
        library_id: librarySlug,
        ...options,
      }),
    });
  },
  importSaved: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetchApi<{ status: string }>("/saved/import", {
      method: "POST",
      body: formData,
    });
  },
  processSaved: () =>
    fetchApi<{ status: string }>("/jobs/saved-process", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  getPosts: (
    params?: Params & {
      page?: number;
      page_size?: number;
      unlinked_only?: boolean;
      search_mode?: "keyword" | "semantic";
      sort_order?: "asc" | "desc";
    },
    options?: RequestOptions,
  ) => fetchApi<PaginatedPosts>(`/posts${toQueryString(params)}`, {}, options),
  linkPosts: (librarySlug: string, postIds: string[]) =>
    fetchApi<{ status: string; linked?: number }>(
      `/libraries/${encodeURIComponent(librarySlug)}/posts/link`,
      {
        method: "POST",
        body: JSON.stringify({ post_ids: postIds }),
      },
    ),
  query: (data: QueryIn, options?: RequestOptions) =>
    fetchApi<QueryResponse>(
      "/query",
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      { timeoutMs: QUERY_TIMEOUT_MS, ...options },
    ),
  checkHealth: (options?: RequestOptions) =>
    fetchApi<{ status: string }>(
      "/health",
      {},
      { timeoutMs: 8_000, ...options },
    ),
  generateChatTitle: (content: string) =>
    fetchApi<{ title: string }>("/chats/title", {
      method: "POST",
      body: JSON.stringify({ role: "user", content }),
    }),
  cancelJob: (jobId: string) =>
    fetchApi<{ status: string }>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),
  getJobs: (options?: RequestOptions) =>
    fetchApi<{ jobs: JobInfo[] }>("/jobs", {}, options),
  getJob: (jobId: string, options?: RequestOptions) =>
    fetchApi<JobInfo>(
      `/jobs/${encodeURIComponent(jobId)}?log_limit=1000`,
      {},
      options,
    ),
  deletePost: (libraryId: string, postId: string) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(libraryId)}/posts/${encodeURIComponent(postId)}`,
      { method: "DELETE" },
    ),
  deletePostsBulk: (libraryId: string, postIds: string[]) =>
    fetchApi<BulkDeleteResponse>(
      `/libraries/${encodeURIComponent(libraryId)}/posts/bulk`,
      {
        method: "DELETE",
        body: JSON.stringify({ post_ids: postIds }),
      },
    ),
  deleteGlobalPost: (postId: string) =>
    fetchApi<{ status: string; deleted_count: number }>(
      `/posts/${encodeURIComponent(postId)}`,
      { method: "DELETE" },
    ),
  deleteGlobalPostsBulk: (postIds: string[]) =>
    fetchApi<{ status: string; deleted_count: number }>("/posts", {
      method: "DELETE",
      body: JSON.stringify({ post_ids: postIds }),
    }),
  deleteSource: (libraryId: string, sourceId: string) =>
    fetchApi<{ status: string }>(
      `/libraries/${encodeURIComponent(libraryId)}/sources/${encodeURIComponent(sourceId)}`,
      { method: "DELETE" },
    ),
  getSources: (
    params?: { library_id?: string; page?: number; page_size?: number },
    options?: RequestOptions,
  ) =>
    fetchApi<{ items: SourceItem[]; total: number }>(
      `/sources${toQueryString(params)}`,
      {},
      options,
    ),
  getLibrarySources: (
    libraryId: string,
    page?: number,
    pageSize?: number,
    options?: RequestOptions,
  ) =>
    fetchApi<{ items: SourceItem[]; total: number }>(
      `/libraries/${encodeURIComponent(libraryId)}/sources${toQueryString({ page, page_size: pageSize })}`,
      {},
      options,
    ),
  getCookiesStatus: (options?: RequestOptions) =>
    fetchApi<CookiesStatus>("/config/cookies", {}, options),
  uploadCookies: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetchApi<{ status: string; size_bytes: number }>("/config/cookies", {
      method: "POST",
      body: formData,
    });
  },
  deleteCookies: () =>
    fetchApi<{ status: string }>("/config/cookies", { method: "DELETE" }),
  reindexSource: (sourceId: string) =>
    fetchApi<{
      status: string;
      source_id: string;
      title: string;
      extracted_knowledge: string;
    }>(
      `/sources/${encodeURIComponent(sourceId)}/reindex`,
      { method: "POST" },
      { timeoutMs: 180_000 },
    ),
};
