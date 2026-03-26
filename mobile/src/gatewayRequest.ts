/**
 * Single entry for gateway-relative paths (same routing contract as web `API_BASE`).
 * Always use paths starting with `/api/v1/...`, `/user/...`, `/login`, etc.
 */
import { authClient } from "./authClient";
import { GATEWAY_BASE_URL } from "./config";
import { formatApiDetail } from "./formatApiDetail";

export function gatewayUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${GATEWAY_BASE_URL}${p}`;
}

export async function gatewayJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authClient.requestWithRefresh(gatewayUrl(path), init);
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(formatApiDetail((data as { detail?: unknown })?.detail, `Request failed (${res.status})`));
  }
  return data as T;
}

/** Same as gatewayJson but returns `{ ok, data }` without throwing (e.g. optional secondary fetches). */
export async function gatewayJsonOptional<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<{ ok: boolean; data: T | null; status: number }> {
  const res = await authClient.requestWithRefresh(gatewayUrl(path), init);
  const data = (await res.json().catch(() => null)) as T | null;
  return { ok: res.ok, data, status: res.status };
}
