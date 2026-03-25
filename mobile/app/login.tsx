import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Button, SafeAreaView, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { GATEWAY_BASE_URL } from "../src/config";
import { authClient } from "../src/authClient";

async function checkGateway(): Promise<boolean> {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), 4000);
  try {
    const res = await fetch(`${GATEWAY_BASE_URL}/health`, { signal: controller.signal });
    return res.ok;
  } finally {
    clearTimeout(t);
  }
}

export default function LoginScreen() {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [gatewayStatus, setGatewayStatus] = useState<
    "unknown" | "reachable" | "unreachable"
  >("unknown");
  const [gatewayChecking, setGatewayChecking] = useState(true);

  useEffect(() => {
    WebBrowser.maybeCompleteAuthSession();
    let cancelled = false;
    (async () => {
      try {
        const ok = await checkGateway();
        if (cancelled) return;
        setGatewayStatus(ok ? "reachable" : "unreachable");
      } catch {
        if (cancelled) return;
        setGatewayStatus("unreachable");
      } finally {
        if (cancelled) return;
        setGatewayChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const gatewayMessage = useMemo(() => {
    if (gatewayChecking) return "Checking gateway...";
    if (gatewayStatus === "reachable") return `Gateway reachable: ${GATEWAY_BASE_URL}`;
    return `Gateway unreachable: ${GATEWAY_BASE_URL}`;
  }, [gatewayChecking, gatewayStatus]);

  const onLogin = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await authClient.login(email.trim(), password);
      router.replace("/(tabs)/");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const startOAuth = async (provider: "google" | "apple") => {
    setError(null);
    setOauthLoading(true);
    try {
      const redirectUri = "pocketii://oauth/callback";
      const authUrl =
        provider === "google"
          ? `${GATEWAY_BASE_URL}/auth/google?mobile=mobile`
          : `${GATEWAY_BASE_URL}/auth/apple?mobile=mobile`;

      await WebBrowser.openAuthSessionAsync(authUrl, redirectUri);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "OAuth start failed.");
    } finally {
      setOauthLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, padding: 20, justifyContent: "center" }}>
      <View style={{ gap: 12 }}>
        <Text style={{ fontSize: 22, fontWeight: "700" }}>Sign in</Text>

        <Text style={{ color: "#64748b", fontSize: 13 }}>{gatewayMessage}</Text>

        <TextInput
          value={email}
          onChangeText={setEmail}
          placeholder="Email"
          autoCapitalize="none"
          keyboardType="email-address"
          style={{
            borderWidth: 1,
            borderColor: "#cbd5e1",
            borderRadius: 10,
            padding: 10,
          }}
        />
        <TextInput
          value={password}
          onChangeText={setPassword}
          placeholder="Password"
          secureTextEntry
          style={{
            borderWidth: 1,
            borderColor: "#cbd5e1",
            borderRadius: 10,
            padding: 10,
          }}
        />

        <View style={{ marginTop: 6, gap: 10 }}>
          <Text style={{ textAlign: "center", color: "#64748b", fontSize: 12 }}>OR</Text>
          <Button
            title={oauthLoading ? "Opening..." : "Continue with Google"}
            onPress={() => startOAuth("google")}
            disabled={oauthLoading || submitting}
          />
          <Button
            title={oauthLoading ? "Opening..." : "Continue with Apple"}
            onPress={() => startOAuth("apple")}
            disabled={oauthLoading || submitting}
          />
        </View>

        {error ? (
          <Text style={{ color: "#dc2626", fontSize: 13 }}>{error}</Text>
        ) : null}

        <View style={{ marginTop: 6 }}>
          {submitting ? (
            <ActivityIndicator />
          ) : (
            <Button
              title="Login"
              onPress={onLogin}
              disabled={!email.trim() || !password || submitting}
            />
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

