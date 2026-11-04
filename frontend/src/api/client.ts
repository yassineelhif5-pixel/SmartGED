/**
 * API client. The access token lives in memory only; the refresh token is an
 * httpOnly cookie handled by the browser. A 401 triggers one silent refresh.
 */
import { useSessionStore } from "@/stores/session";
import type { Session } from "@/types/api";

export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

let refreshing: Promise<Session | null> | null = null;

export async function refreshSession(): Promise<Session | null> {
  if (!refreshing) {
    refreshing = fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" })
      .then(async (r) => (r.ok ? ((await r.json()) as Session) : null))
      .catch(() => null)
      .then((s) => {
        useSessionStore.getState().setSession(s);
        return s;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; query?: Record<string, unknown>; raw?: boolean };

function buildUrl(path: string, query?: Record<string, unknown>) {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  Object.entries(query ?? {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, String(item)));
    else url.searchParams.set(k, String(v));
  });
  return url.toString();
}

export async function api<T>(path: string, opts: Options = {}, retry = true): Promise<T> {
  const token = useSessionStore.getState().session?.access_token;
  const headers = new Headers(opts.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(buildUrl(path, opts.query), { ...opts, headers, body, credentials: "include" });
  if (res.status === 401 && retry && !path.startsWith("/auth/login")) {
    const s = await refreshSession();
    if (s) return api<T>(path, opts, false);
  }
  if (!res.ok) {
    let payload: { error?: { code: string; message: string; details?: unknown } } = {};
    try {
      payload = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(
      res.status,
      payload.error?.code ?? "http_error",
      payload.error?.message ?? `Erreur ${res.status}`,
      payload.error?.details,
    );
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch a protected file as a Blob (used for previews and downloads). */
export async function fetchBlob(path: string, query?: Record<string, unknown>): Promise<Blob> {
  const res = await api<Response>(path, { raw: true, query });
  return res.blob();
}

export async function downloadFile(path: string, filename: string, query?: Record<string, unknown>) {
  const blob = await fetchBlob(path, query);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
