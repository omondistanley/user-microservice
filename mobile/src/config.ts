/**
 * Point at the same API gateway URL as the web app (e.g. https://api.example.com).
 * Override with EXPO_PUBLIC_GATEWAY_URL in a .env for local dev.
 */
export const GATEWAY_BASE_URL =
  (typeof process !== "undefined" && process.env?.EXPO_PUBLIC_GATEWAY_URL) ||
  "http://localhost:8080";
