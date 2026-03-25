import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../src/config";
import { authClient } from "../src/authClient";
import { theme } from "../src/theme";

const OTP_LEN = 6;

function maskEmail(raw: string): string {
  const s = raw.trim();
  const at = s.indexOf("@");
  if (at < 1) return s || "your email";
  const user = s.slice(0, at);
  const domain = s.slice(at + 1);
  if (user.length <= 2) return `${user[0] ?? "*"}***@${domain}`;
  return `${user[0]}***${user.slice(-1)}@${domain}`;
}

type Me = { email?: string; email_verified_at?: string | null };

export default function VerifyEmailScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [me, setMe] = useState<Me | null>(null);
  const [loadingMe, setLoadingMe] = useState(true);
  const [digits, setDigits] = useState<string[]>(() => Array(OTP_LEN).fill(""));
  const refs = useRef<Array<TextInput | null>>([]);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMe = useCallback(async () => {
    setLoadingMe(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/user/me`, { method: "GET" });
      const json = (await res.json().catch(() => null)) as Me | null;
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Could not load profile.");
      setMe(json);
      if (json?.email_verified_at) {
        router.replace("/(tabs)/profile");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load profile.");
    } finally {
      setLoadingMe(false);
    }
  }, [router]);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const masked = useMemo(() => maskEmail(me?.email ?? ""), [me?.email]);

  const setDigitAt = (index: number, char: string) => {
    const c = char.replace(/\D/g, "").slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[index] = c;
      return next;
    });
    if (c && index < OTP_LEN - 1) {
      refs.current[index + 1]?.focus();
    }
  };

  const onKeyPress = (index: number, key: string) => {
    if (key === "Backspace") {
      setDigits((prev) => {
        const next = [...prev];
        if (next[index]) next[index] = "";
        else if (index > 0) {
          next[index - 1] = "";
          refs.current[index - 1]?.focus();
        }
        return next;
      });
    }
  };

  const onVerify = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/user/me`, { method: "GET" });
      const json = (await res.json().catch(() => null)) as Me | null;
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Verification check failed.");
      if (json?.email_verified_at) {
        router.replace("/(tabs)/");
        return;
      }
      setError("Your email is not verified yet. Open the verification link from your inbox, then tap Verify again.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  const onResend = async () => {
    setResending(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/users/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const json = await res.json().catch(() => null);
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Could not resend email.");
      }
      setMessage("If your account needs verification, a new email is on the way.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Resend failed.");
    } finally {
      setResending(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: insets.top }]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <MaterialCommunityIcons name="email-check-outline" size={40} color={theme.colors.primary} />
          </View>
          <Text style={styles.title}>Check your inbox</Text>
          <Text style={styles.body}>
            We&apos;ve sent a verification link to <Text style={styles.emph}>{masked}</Text>. Open it on your
            device, then return here and tap Verify and Continue. Need another message? Tap Resend Email.
          </Text>

          <View style={styles.otpRow}>
            {digits.map((d, i) => (
              <TextInput
                key={i}
                ref={(r) => {
                  refs.current[i] = r;
                }}
                value={d}
                onChangeText={(t) => setDigitAt(i, t)}
                onKeyPress={({ nativeEvent }) => onKeyPress(i, nativeEvent.key)}
                keyboardType="number-pad"
                maxLength={1}
                style={[styles.otpCell, i === digits.findIndex((x) => !x) && styles.otpCellFocus]}
                placeholder="•"
                placeholderTextColor={theme.colors.outline}
              />
            ))}
          </View>

          {message ? <Text style={styles.info}>{message}</Text> : null}
          {error ? <Text style={styles.err}>{error}</Text> : null}

          <Pressable style={styles.primary} onPress={onVerify} disabled={busy || loadingMe}>
            {busy ? (
              <ActivityIndicator color={theme.colors.onPrimary} />
            ) : (
              <Text style={styles.primaryTxt}>Verify and Continue</Text>
            )}
          </Pressable>

          <View style={styles.resendBlock}>
            <Text style={styles.resendK}>Didn&apos;t receive the email?</Text>
            <Pressable onPress={onResend} disabled={resending}>
              <Text style={styles.resendLink}>{resending ? "Sending…" : "Resend Email"}</Text>
            </Pressable>
          </View>

          <View style={styles.footerRule} />
          <View style={styles.footerRow}>
            <View style={styles.footerItem}>
              <MaterialCommunityIcons name="shield-check-outline" size={18} color={theme.colors.secondary} />
              <Text style={styles.footerCaps}>Secure Session</Text>
            </View>
            <Pressable
              style={styles.footerItem}
              onPress={() => router.push("/more")}
            >
              <MaterialCommunityIcons name="help-circle-outline" size={18} color={theme.colors.secondary} />
              <Text style={styles.footerCaps}>Support</Text>
            </Pressable>
          </View>
        </View>

        {loadingMe ? <ActivityIndicator style={{ marginTop: 16 }} /> : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, justifyContent: "center", paddingHorizontal: theme.spacing.xl },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.xl,
    padding: theme.spacing.xxl,
    ...theme.shadows.md,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  iconWrap: {
    alignSelf: "center",
    width: 72,
    height: 72,
    borderRadius: 18,
    backgroundColor: theme.colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: theme.spacing.lg,
  },
  title: {
    fontSize: 24,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    textAlign: "center",
    marginBottom: 10,
  },
  body: {
    fontSize: 14,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    textAlign: "center",
    lineHeight: 20,
    marginBottom: 22,
  },
  emph: { fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  otpRow: { flexDirection: "row", justifyContent: "space-between", gap: 6, marginBottom: 22 },
  otpCell: {
    flex: 1,
    maxWidth: 48,
    height: 56,
    borderRadius: 12,
    backgroundColor: theme.colors.surfaceContainer,
    textAlign: "center",
    fontSize: 22,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    borderWidth: 2,
    borderColor: "transparent",
  },
  otpCellFocus: { borderColor: theme.colors.primary, backgroundColor: theme.colors.surfaceContainerLow },
  info: { color: theme.colors.primary, fontFamily: "Inter_600SemiBold", fontSize: 12, textAlign: "center", marginBottom: 8 },
  err: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", fontSize: 12, textAlign: "center", marginBottom: 8 },
  primary: {
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    alignItems: "center",
    ...theme.shadows.md,
  },
  primaryTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 16 },
  resendBlock: { alignItems: "center", marginTop: 18, gap: 6 },
  resendK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  resendLink: { fontFamily: "Inter_700Bold", fontSize: 15, color: theme.colors.primary },
  footerRule: {
    marginTop: 28,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.outlineVariant,
  },
  footerRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 28,
    marginTop: 16,
  },
  footerItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  footerCaps: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
});
