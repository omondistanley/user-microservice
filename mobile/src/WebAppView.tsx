import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, View } from "react-native";
import { WebView } from "react-native-webview";
import { getAccessToken, getRefreshToken } from "./authTokens";
import { GATEWAY_BASE_URL } from "./config";

export default function WebAppView({ path }: { path: string }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [loadingTokens, setLoadingTokens] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const a = await getAccessToken();
        const r = await getRefreshToken();
        if (cancelled) return;
        setAccessToken(a);
        setRefreshToken(r);
      } finally {
        if (!cancelled) setLoadingTokens(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const uri = useMemo(() => {
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${GATEWAY_BASE_URL}${p}`;
  }, [path]);

  const beforeContentLoadedJS = useMemo(() => {
    const a = accessToken ?? "";
    const r = refreshToken ?? "";
    // Keep injection minimal: set localStorage tokens so the web auth layer works.
    return `
      (function () {
        try {
          localStorage.setItem("access_token", ${JSON.stringify(a)});
          localStorage.setItem("refresh_token", ${JSON.stringify(r)});
          // Ensure the web app uses the reachable gateway for API calls.
          window.API_BASE = ${JSON.stringify(GATEWAY_BASE_URL)};
          window.EXPENSE_API_BASE = "";
          window.BUDGET_API_BASE = "";
        } catch (e) {}
      })();
      true;
    `;
  }, [accessToken, refreshToken]);

  const injectedJS = useMemo(() => {
    // Secondary pass: update meta tag if it exists.
    return `
      (function () {
        try {
          var apiBase = ${JSON.stringify(GATEWAY_BASE_URL)};
          var meta = document.querySelector('meta[name="gateway-public-url"]');
          if (meta) meta.setAttribute("content", apiBase);
        } catch (e) {}
      })();
      true;
    `;
  }, []);

  if (loadingTokens) {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <WebView
      source={{ uri }}
      injectedJavaScriptBeforeContentLoaded={beforeContentLoadedJS}
      injectedJavaScript={injectedJS}
      javaScriptEnabled
      domStorageEnabled
      startInLoadingState
    />
  );
}

