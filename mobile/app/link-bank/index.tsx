import React, { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as WebBrowser from "expo-web-browser";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as SecureStore from "expo-secure-store";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

const PLAID_LINK_TOKEN_KEY = "pocketii_plaid_link_token";

const POPULAR = [
  { name: "Chase", abbr: "C", color: "#1d4ed8" },
  { name: "Bank of America", abbr: "BA", color: "#e11d48" },
  { name: "Wells Fargo", abbr: "WF", color: "#ca8a04" },
  { name: "Citibank", abbr: "Ci", color: "#0369a1" },
  { name: "Capital One", abbr: "C1", color: "#7f1d1d" },
  { name: "U.S. Bank", abbr: "US", color: "#0f172a" },
] as const;

const MORE = ["Ally Bank", "American Express", "Barclays", "Charles Schwab"] as const;

export default function LinkBankStartScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const completionUri = useMemo(() => "pocketii://link-bank/success", []);

  const start = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/link-hosted`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ completion_redirect_uri: completionUri }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to start link.");

      const linkToken = json?.link_token ? String(json.link_token) : "";
      const hostedUrl = json?.hosted_link_url ? String(json.hosted_link_url) : "";
      if (!linkToken || !hostedUrl) throw new Error("Plaid hosted link response missing fields.");

      await SecureStore.setItemAsync(PLAID_LINK_TOKEN_KEY, linkToken);
      await WebBrowser.openBrowserAsync(hostedUrl);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to start bank linking.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={[styles.safe, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle}>Link Bank Account</Text>
        <Pressable hitSlop={12} style={styles.help}>
          <MaterialCommunityIcons name="help-circle-outline" size={24} color={theme.colors.primary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + 24 }]}>
        <View style={styles.banner}>
          <MaterialCommunityIcons name="shield-lock-outline" size={28} color={theme.colors.primary} />
          <View style={{ flex: 1 }}>
            <Text style={styles.bannerTitle}>Secure connection</Text>
            <Text style={styles.bannerBody}>
              PocketII uses bank-grade encryption. We never store your bank login on the device.
            </Text>
          </View>
        </View>

        <View style={styles.searchWrap}>
          <MaterialCommunityIcons name="magnify" size={20} color={theme.colors.secondary} />
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder="Search for your bank or credit union"
            placeholderTextColor={theme.colors.secondary}
            style={styles.searchIn}
          />
        </View>

        <View style={styles.rowHead}>
          <Text style={styles.h2}>Popular banks</Text>
          <Text style={styles.h2Accent}>Most used</Text>
        </View>
        <View style={styles.grid}>
          {POPULAR.map((b) => (
            <Pressable key={b.name} style={styles.bankCard} onPress={start} disabled={loading}>
              <View style={[styles.bankIcon, { backgroundColor: b.color }]}>
                <Text style={styles.bankAbbr}>{b.abbr}</Text>
              </View>
              <Text style={styles.bankName}>{b.name}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={[styles.h2, { marginTop: 8 }]}>All institutions</Text>
        {MORE.filter((n) => n.toLowerCase().includes(q.trim().toLowerCase())).map((n) => (
          <Pressable key={n} style={styles.listRow} onPress={start} disabled={loading}>
            <View style={styles.listIcon}>
              <MaterialCommunityIcons name="bank-outline" size={22} color={theme.colors.secondary} />
            </View>
            <Text style={styles.listName}>{n}</Text>
            <MaterialCommunityIcons name="chevron-right" size={22} color={theme.colors.secondary} />
          </Pressable>
        ))}

        <View style={styles.trust}>
          <View style={styles.trustItem}>
            <MaterialCommunityIcons name="check-decagram" size={18} color={theme.colors.secondary} />
            <Text style={styles.trustTxt}>Verified</Text>
          </View>
          <View style={styles.trustItem}>
            <MaterialCommunityIcons name="lock" size={18} color={theme.colors.secondary} />
            <Text style={styles.trustTxt}>Encrypted</Text>
          </View>
        </View>
        <Text style={styles.legal}>
          By linking, you agree to our Terms and authorize read access via Plaid.
        </Text>
        <Text style={styles.plaid}>Powered by PLAID</Text>

        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Pressable style={styles.cta} onPress={start} disabled={loading}>
          {loading ? (
            <ActivityIndicator color={theme.colors.onPrimary} />
          ) : (
            <Text style={styles.ctaTxt}>Continue with Plaid</Text>
          )}
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.surface },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  topTitle: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  help: {
    width: 40,
    height: 40,
    borderRadius: 999,
    backgroundColor: `${theme.colors.primary}14`,
    alignItems: "center",
    justifyContent: "center",
  },
  container: { paddingHorizontal: theme.spacing.xl, paddingTop: 16, gap: 14 },
  banner: {
    flexDirection: "row",
    gap: 12,
    backgroundColor: theme.colors.primaryFixed,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    alignItems: "flex-start",
  },
  bannerTitle: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  bannerBody: { marginTop: 4, fontSize: 13, color: theme.colors.onSurfaceVariant, lineHeight: 18 },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: theme.radii.lg,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: theme.colors.surfaceContainerLow,
  },
  searchIn: { flex: 1, fontSize: 15, fontFamily: "Inter_400Regular", color: theme.colors.onSurface },
  rowHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  h2: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  h2Accent: { fontSize: 11, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary, letterSpacing: 1 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  bankCard: {
    width: "31%",
    minWidth: 100,
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: theme.radii.lg,
    padding: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  bankIcon: {
    width: 44,
    height: 44,
    borderRadius: theme.radii.md,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  bankAbbr: { color: "#fff", fontFamily: "Inter_800ExtraBold", fontSize: 14 },
  bankName: { fontSize: 11, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface, textAlign: "center" },
  listRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  listIcon: {
    width: 40,
    height: 40,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  listName: { flex: 1, fontSize: 15, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  trust: { flexDirection: "row", justifyContent: "center", gap: 24, marginTop: 16 },
  trustItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  trustTxt: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.secondary },
  legal: {
    textAlign: "center",
    fontSize: 11,
    color: theme.colors.secondary,
    lineHeight: 16,
    marginTop: 8,
  },
  plaid: {
    textAlign: "center",
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    marginTop: 4,
    letterSpacing: 1,
  },
  error: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", textAlign: "center" },
  cta: {
    marginTop: 12,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    alignItems: "center",
  },
  ctaTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 16 },
});
