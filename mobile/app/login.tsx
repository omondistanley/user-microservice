import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import * as AuthSession from "expo-auth-session";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../src/config";
import { authClient } from "../src/authClient";
import { theme } from "../src/theme";

type Mode = "login" | "register";

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
  const insets = useSafeAreaInsets();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [oauthLoading, setOauthLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [gatewayStatus, setGatewayStatus] = useState<"unknown" | "reachable" | "unreachable">("unknown");
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

  const gatewayHint = useMemo(() => {
    if (gatewayChecking) return "Checking connection…";
    if (gatewayStatus === "reachable") return null;
    return `Cannot reach ${GATEWAY_BASE_URL}`;
  }, [gatewayChecking, gatewayStatus]);

  const onLogin = async () => {
    setSubmitting(true);
    setError(null);
    setInfo(null);
    try {
      await authClient.login(email.trim(), password);
      router.replace("/(tabs)/");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const onRegister = async () => {
    setSubmitting(true);
    setError(null);
    setInfo(null);
    try {
      const res = await fetch(`${GATEWAY_BASE_URL}/user`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          password,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail ? String(data.detail) : "Registration failed.");
      }
      await authClient.login(email.trim(), password);
      router.replace("/(tabs)/");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Registration failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const onForgot = async () => {
    setError(null);
    setInfo(null);
    const em = email.trim();
    if (!em) {
      setError("Enter your email, then tap Forgot password.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${GATEWAY_BASE_URL}/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: em }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.detail ? String(data.detail) : "Request failed.");
      }
      setInfo(
        typeof data?.message === "string"
          ? data.message
          : "If an account exists for this email, you will receive a reset link.",
      );
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Could not start password reset.");
    } finally {
      setSubmitting(false);
    }
  };

  const startOAuth = async (provider: "google" | "apple") => {
    setError(null);
    setOauthLoading(true);
    try {
      const redirectUri = AuthSession.makeRedirectUri({
        scheme: "pocketii",
        path: "oauth/callback",
      });
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

  const primaryDisabled =
    submitting ||
    oauthLoading ||
    !email.trim() ||
    !password ||
    (mode === "register" && (!firstName.trim() || !lastName.trim() || password.length < 8));

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 32 },
        ]}
      >
        <View style={styles.mobileBrand}>
          <View style={styles.brandIcon}>
            <MaterialCommunityIcons name="shield-check" size={22} color={theme.colors.onPrimary} />
          </View>
          <Text style={styles.brandText}>Indigo Vault</Text>
        </View>

        <Text style={styles.welcome}>{mode === "login" ? "Welcome Back" : "Create your account"}</Text>
        <Text style={styles.sub}>
          {mode === "login"
            ? "Access your institutional vault and assets."
            : "Set up secure access with your work email and a strong password."}
        </Text>

        {gatewayHint ? <Text style={styles.gatewayWarn}>{gatewayHint}</Text> : null}

        <View style={styles.segment}>
          <Pressable
            style={[styles.segmentBtn, mode === "login" && styles.segmentActive]}
            onPress={() => {
              setMode("login");
              setError(null);
            }}
          >
            <Text style={[styles.segmentLabel, mode === "login" && styles.segmentLabelActive]}>Login</Text>
          </Pressable>
          <Pressable
            style={[styles.segmentBtn, mode === "register" && styles.segmentActive]}
            onPress={() => {
              setMode("register");
              setError(null);
            }}
          >
            <Text style={[styles.segmentLabel, mode === "register" && styles.segmentLabelActive]}>
              Create Account
            </Text>
          </Pressable>
        </View>

        {mode === "register" ? (
          <>
            <Text style={styles.fieldLabel}>First name</Text>
            <TextInput
              value={firstName}
              onChangeText={setFirstName}
              placeholder="Jane"
              placeholderTextColor={theme.colors.secondary}
              style={styles.input}
            />
            <Text style={[styles.fieldLabel, { marginTop: 14 }]}>Last name</Text>
            <TextInput
              value={lastName}
              onChangeText={setLastName}
              placeholder="Doe"
              placeholderTextColor={theme.colors.secondary}
              style={styles.input}
            />
          </>
        ) : null}

        <Text style={[styles.fieldLabel, { marginTop: mode === "register" ? 14 : 20 }]}>Email address</Text>
        <View style={styles.inputWrap}>
          <MaterialCommunityIcons
            name="email-outline"
            size={20}
            color={theme.colors.onSurfaceVariant}
            style={styles.inputIcon}
          />
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="name@company.com"
            placeholderTextColor={theme.colors.secondary}
            autoCapitalize="none"
            keyboardType="email-address"
            style={styles.inputInner}
          />
        </View>

        <View style={styles.pwLabelRow}>
          <Text style={styles.fieldLabel}>Password</Text>
          {mode === "login" ? (
            <Pressable onPress={onForgot} hitSlop={8}>
              <Text style={styles.forgot}>Forgot password?</Text>
            </Pressable>
          ) : (
            <Text style={styles.forgotMuted}>Min 8 characters</Text>
          )}
        </View>
        <View style={styles.inputWrap}>
          <MaterialCommunityIcons
            name="lock-outline"
            size={20}
            color={theme.colors.onSurfaceVariant}
            style={styles.inputIcon}
          />
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor={theme.colors.secondary}
            secureTextEntry={!showPassword}
            style={styles.inputInner}
          />
          <Pressable style={styles.eye} onPress={() => setShowPassword((s) => !s)}>
            <MaterialCommunityIcons
              name={showPassword ? "eye-off-outline" : "eye-outline"}
              size={22}
              color={theme.colors.onSurfaceVariant}
            />
          </Pressable>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        {info ? <Text style={styles.info}>{info}</Text> : null}

        <Pressable
          style={[styles.primary, primaryDisabled && { opacity: 0.55 }]}
          disabled={primaryDisabled}
          onPress={mode === "login" ? onLogin : onRegister}
        >
          {submitting ? (
            <ActivityIndicator color={theme.colors.onPrimary} />
          ) : (
            <Text style={styles.primaryText}>
              {mode === "login" ? "Login to Vault" : "Create account"}
            </Text>
          )}
        </Pressable>

        <View style={styles.dividerRow}>
          <View style={styles.divider} />
          <Text style={styles.dividerCaps}>Or continue with</Text>
          <View style={styles.divider} />
        </View>

        <View style={styles.socialRow}>
          <Pressable
            style={[styles.socialBtn, oauthLoading && { opacity: 0.6 }]}
            disabled={oauthLoading || submitting}
            onPress={() => startOAuth("google")}
          >
            <MaterialCommunityIcons name="google" size={22} color="#4285F4" />
            <Text style={styles.socialLabel}>Google</Text>
          </Pressable>
          <Pressable
            style={[styles.socialBtn, oauthLoading && { opacity: 0.6 }]}
            disabled={oauthLoading || submitting}
            onPress={() => startOAuth("apple")}
          >
            <MaterialCommunityIcons name="apple" size={22} color={theme.colors.onSurface} />
            <Text style={styles.socialLabel}>Apple</Text>
          </Pressable>
        </View>

        <Text style={styles.footer}>
          Security guaranteed by Indigo Vault{"\n"}
          <Text style={styles.footerDim}>AES-256 bit encryption standard</Text>
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { paddingHorizontal: theme.spacing.xxl, maxWidth: 520, width: "100%", alignSelf: "center" },
  mobileBrand: { flexDirection: "row", alignItems: "center", gap: 10, marginBottom: 28 },
  brandIcon: {
    width: 36,
    height: 36,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  brandText: {
    fontSize: 20,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: -0.4,
  },
  welcome: {
    fontSize: 28,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginBottom: 6,
  },
  sub: {
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    marginBottom: 10,
  },
  gatewayWarn: {
    fontSize: 12,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.tertiary,
    marginBottom: 12,
  },
  segment: {
    flexDirection: "row",
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: 999,
    padding: 4,
    marginBottom: 22,
    marginTop: 10,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 999,
    alignItems: "center",
  },
  segmentActive: {
    backgroundColor: theme.colors.surface,
    ...theme.shadows.sm,
  },
  segmentLabel: {
    fontSize: 14,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
  },
  segmentLabelActive: { color: theme.colors.primary },
  fieldLabel: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.8,
    textTransform: "uppercase",
    marginBottom: 8,
    marginLeft: 4,
  },
  input: {
    backgroundColor: theme.colors.surfaceContainerLow,
    borderRadius: theme.radii.lg,
    paddingHorizontal: 16,
    paddingVertical: 16,
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
  },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.surfaceContainerLow,
    borderRadius: theme.radii.lg,
    paddingRight: 12,
  },
  inputIcon: { marginLeft: 14 },
  inputInner: {
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 16,
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
  },
  eye: { padding: 8 },
  pwLabelRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 18,
    marginBottom: 8,
    paddingHorizontal: 4,
  },
  forgot: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  forgotMuted: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.secondary,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  error: {
    marginTop: 12,
    color: theme.colors.error,
    fontFamily: "Inter_600SemiBold",
    fontSize: 13,
  },
  info: {
    marginTop: 12,
    color: theme.colors.onPrimaryContainer,
    fontFamily: "Inter_600SemiBold",
    fontSize: 13,
  },
  primary: {
    marginTop: 22,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    alignItems: "center",
    ...theme.shadows.md,
  },
  primaryText: {
    color: theme.colors.onPrimary,
    fontSize: 18,
    fontFamily: "Inter_800ExtraBold",
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 28,
    gap: 12,
  },
  divider: { flex: 1, height: 1, backgroundColor: theme.colors.outlineVariant },
  dividerCaps: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.6,
    textTransform: "uppercase",
  },
  socialRow: { flexDirection: "row", gap: 12 },
  socialBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 16,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.surface,
  },
  socialLabel: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  footer: {
    marginTop: 36,
    textAlign: "center",
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    lineHeight: 18,
  },
  footerDim: {
    fontFamily: "Inter_500Medium",
    textTransform: "uppercase",
    opacity: 0.65,
    letterSpacing: 1.2,
  },
});
