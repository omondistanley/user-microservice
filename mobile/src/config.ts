import Constants from "expo-constants";
import { Platform } from "react-native";

/**
 * Point at the same API gateway URL as the web app (e.g. https://api.example.com).
 * Override with EXPO_PUBLIC_GATEWAY_URL in a .env for local dev.
 */
const envGatewayUrl =
  typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_GATEWAY_URL : undefined;

function pickHostFromExpoRuntime(): string | null {
  const hostCandidates = [
    Constants.expoConfig?.hostUri,
    (Constants.manifest2 as { extra?: { expoGo?: { debuggerHost?: string } } } | null)
      ?.extra?.expoGo?.debuggerHost,
  ];

  for (const candidate of hostCandidates) {
    if (!candidate) {
      continue;
    }
    const host = candidate.split(":")[0]?.trim();
    if (host) {
      return host;
    }
  }
  return null;
}

function resolveGatewayBaseUrl(): string {
  if (envGatewayUrl) {
    try {
      const parsed = new URL(envGatewayUrl);
      if (__DEV__ && parsed.port === "8081") {
        parsed.port = "8080";
        console.warn(
          `[mobile] EXPO_PUBLIC_GATEWAY_URL was set to Metro port 8081; using ${parsed.toString()} instead.`,
        );
        return parsed.toString().replace(/\/$/, "");
      }
      return envGatewayUrl;
    } catch {
      if (__DEV__) {
        console.warn(
          `[mobile] EXPO_PUBLIC_GATEWAY_URL is invalid (${envGatewayUrl}). Falling back to auto-detected host.`,
        );
      }
    }
  }

  const detectedHost = pickHostFromExpoRuntime();
  if (detectedHost) {
    return `http://${detectedHost}:8080`;
  }

  if (Platform.OS === "android") {
    return "http://10.0.2.2:8080";
  }

  return "http://localhost:8080";
}

export const GATEWAY_BASE_URL = resolveGatewayBaseUrl();

if (__DEV__) {
  console.log(`[mobile] gateway base URL: ${GATEWAY_BASE_URL}`);
}
