import { GATEWAY_BASE_URL } from "./config";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from "./authTokens";

type TokenResponse = {
  access_token: string;
  token_type?: string;
  refresh_token?: string | null;
};

async function parseJsonSafe(res: Response): Promise<any | null> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function getErrorDetail(res: Response, data: any | null): string {
  if (data && typeof data.detail === "string") return data.detail;
  if (res.statusText) return res.statusText;
  return `Request failed with status ${res.status}`;
}

async function refreshAccessTokenOnce(): Promise<TokenResponse> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    throw new Error("No refresh token available.");
  }

  const res = await fetch(`${GATEWAY_BASE_URL}/token/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  const data = await parseJsonSafe(res);
  if (!res.ok) {
    throw new Error(getErrorDetail(res, data));
  }

  const tokenData = data as TokenResponse;
  if (!tokenData?.access_token) {
    throw new Error("Refresh did not return access_token.");
  }

  await setTokens(
    String(tokenData.access_token),
    tokenData.refresh_token ? String(tokenData.refresh_token) : undefined,
  );
  return tokenData;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams({ username: email, password });

  const res = await fetch(`${GATEWAY_BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  const data = await parseJsonSafe(res);
  if (!res.ok) {
    throw new Error(getErrorDetail(res, data));
  }

  const tokenData = data as TokenResponse;
  if (!tokenData?.access_token) {
    throw new Error("Login did not return access_token.");
  }

  await setTokens(
    String(tokenData.access_token),
    tokenData.refresh_token ? String(tokenData.refresh_token) : undefined,
  );
  return tokenData;
}

export async function restoreSession(): Promise<boolean> {
  const accessToken = await getAccessToken();
  if (accessToken) return true;

  const refreshToken = await getRefreshToken();
  if (!refreshToken) return false;

  try {
    await refreshAccessTokenOnce();
    return true;
  } catch {
    await clearTokens();
    return false;
  }
}

export async function requestWithRefresh(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const accessToken = await getAccessToken();
  const headers: Record<string, string> = {
    ...(options.headers ? (options.headers as Record<string, string>) : {}),
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const res = await fetch(url, { ...options, headers });
  if (res.status !== 401) return res;

  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    await clearTokens();
    return res;
  }

  // Retry once after refresh.
  try {
    await refreshAccessTokenOnce();
    const newAccessToken = await getAccessToken();
    if (newAccessToken) {
      headers.Authorization = `Bearer ${newAccessToken}`;
    }
    return await fetch(url, { ...options, headers });
  } catch {
    await clearTokens();
    return res;
  }
}

export const authClient = {
  login,
  restoreSession,
  requestWithRefresh,
};

