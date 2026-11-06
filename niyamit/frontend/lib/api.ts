"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Error with the server's plain-language message (FastAPI `detail`). */
export class ApiError extends Error {
  status: number;
  retryAfterSeconds: number | null;
  constructor(status: number, message: string, retryAfterSeconds: number | null = null) {
    super(message);
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

type Options = { method?: string; body?: unknown; form?: FormData };

/** All requests go through the Next.js proxy (/api -> backend), so session cookies stay first-party.
 *  The custom header is the CSRF guard the backend requires on every change. */
export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const hasJson = opts.body !== undefined;
  const res = await fetch(`/api${path}`, {
    method: opts.method ?? (hasJson || opts.form ? "POST" : "GET"),
    headers: { "X-Niyamit-Client": "web", ...(hasJson ? { "Content-Type": "application/json" } : {}) },
    body: opts.form ?? (hasJson ? JSON.stringify(opts.body) : undefined),
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) message = `Check the form: ${body.detail[0].msg}`;
    } catch {
      /* not JSON */
    }
    if (res.status >= 500) message = "The server had a problem. Try again in a moment.";
    const rawRetry = res.headers.get("Retry-After");
    let retry: number | null = null;
    if (rawRetry) {
      const seconds = /^\d+$/.test(rawRetry) ? Number(rawRetry) : Math.ceil((Date.parse(rawRetry) - Date.now()) / 1000);
      if (Number.isFinite(seconds)) retry = Math.max(1, Math.min(86400, seconds));
    }
    throw new ApiError(res.status, message, retry);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const current = useRef(path);
  current.current = path;

  const reload = useCallback(async () => {
    if (!path) return null;
    setLoading(true);
    try {
      const result = await api<T>(path);
      if (current.current === path) {
        setData(result);
        setError(null);
      }
      return result;
    } catch (e) {
      if (current.current === path) setError(e instanceof ApiError ? e : new ApiError(0, "Network error."));
      return null;
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** Re-run `tick` every `ms` while `active` is true (used while background work is still running). */
export function usePoll(active: boolean, tick: () => unknown, ms = 1500) {
  const saved = useRef(tick);
  saved.current = tick;
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => void saved.current(), ms);
    return () => window.clearInterval(id);
  }, [active, ms]);
}

export function clientKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `k-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}
