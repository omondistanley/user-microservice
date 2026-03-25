import React, { useEffect, useState } from "react";
import { ActivityIndicator, SafeAreaView, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { setTokens } from "../../src/authTokens";

type OAuthCallbackParams = {
  provider?: string;
  code?: string;
  marker?: string;
};

export default function OAuthCallbackScreen() {
  const router = useRouter();
  const params = useLocalSearchParams() as OAuthCallbackParams;

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const provider = params.provider ? String(params.provider) : "";
        const code = params.code ? String(params.code) : "";
        const marker = params.marker ? String(params.marker) : "";

        if (!provider || !marker) {
          throw new Error("Missing OAuth callback parameters.");
        }
        // Google mobile flow passes the authorization code.
        // Apple mobile flow issues tokens in the Apple callback itself and may not include a code.
        if (provider === "google" && !code) {
          throw new Error("Missing OAuth authorization code.");
        }

        console.log(`[mobile][oauth callback] provider=${provider}`);
        const res = await fetch(`${GATEWAY_BASE_URL}/api/v1/auth/oauth/exchange`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider, code, marker }),
        });

        const data = await res.json().catch(() => null);
        if (!res.ok) {
          console.warn(`[mobile][oauth callback] exchange failed ok=false status=${res.status}`);
          throw new Error(data?.detail ? String(data.detail) : "Token exchange failed.");
        }

        const accessToken = data?.access_token ? String(data.access_token) : "";
        const refreshToken = data?.refresh_token ? String(data.refresh_token) : undefined;
        if (!accessToken) {
          throw new Error("Exchange returned no access_token.");
        }

        await setTokens(accessToken, refreshToken);
        if (cancelled) return;
        router.replace("/(tabs)/");
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "OAuth callback failed.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <SafeAreaView style={{ flex: 1, padding: 20, justifyContent: "center" }}>
      <View style={{ alignItems: "center" }}>
        {error ? (
          <>
            <Text style={{ color: "#dc2626", textAlign: "center" }}>{error}</Text>
            <Text style={{ marginTop: 10, color: "#64748b" }}>
              You can return to login and try again.
            </Text>
          </>
        ) : (
          <>
            <ActivityIndicator />
            <Text style={{ marginTop: 12, color: "#64748b" }}>
              Finishing sign-in...
            </Text>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

