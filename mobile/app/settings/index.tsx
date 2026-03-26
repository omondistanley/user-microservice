import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

type SettingsResponse = {
  default_currency?: string;
  active_household_id?: string | null;
};

type Me = { email?: string };

const CURRENCIES = ["USD", "EUR", "GBP"] as const;
type Currency = (typeof CURRENCIES)[number];

export default function SettingsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [currency, setCurrency] = useState<Currency>("USD");
  const [saving, setSaving] = useState(false);

  const [pushOn, setPushOn] = useState(true);
  const [emailOn, setEmailOn] = useState(false);
  const [darkOn, setDarkOn] = useState(false);
  const [twoFaOn, setTwoFaOn] = useState(true);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, m] = await Promise.all([
        authClient.requestJsonWithRefresh<SettingsResponse>(`${GATEWAY_BASE_URL}/api/v1/settings`, { method: "GET" }),
        authClient.requestJsonWithRefresh<Me>(`${GATEWAY_BASE_URL}/user/me`, { method: "GET" }),
      ]);
      setSettings(s);
      setMe(m);
      const c = String(s?.default_currency ?? "USD").toUpperCase();
      if ((CURRENCIES as readonly string[]).includes(c)) setCurrency(c as Currency);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveCurrency = async () => {
    setSaving(true);
    setError(null);
    try {
      const json = await authClient.requestJsonWithRefresh<SettingsResponse>(`${GATEWAY_BASE_URL}/api/v1/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ default_currency: currency }),
      });
      setSettings(json);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  const VersionFooter = useMemo(
    () => (
      <Text style={styles.version}>
        pocketii v3.4.2 (production){"\n"}© 2025 pocketii
      </Text>
    ),
    [],
  );

  const Row = ({
    icon,
    title,
    subtitle,
    onPress,
    right,
  }: {
    icon: keyof typeof MaterialCommunityIcons.glyphMap;
    title: string;
    subtitle?: string;
    onPress?: () => void;
    right?: React.ReactNode;
  }) => (
    <Pressable style={styles.row} onPress={onPress} disabled={!onPress}>
      <View style={styles.rowIcon}>
        <MaterialCommunityIcons name={icon} size={22} color={theme.colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.rowSub}>{subtitle}</Text> : null}
      </View>
      {right ?? (onPress ? <MaterialCommunityIcons name="chevron-right" size={22} color={theme.colors.secondary} /> : null)}
    </Pressable>
  );

  return (
    <View style={[styles.root, { backgroundColor: theme.colors.background }]}>
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 40 },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backRow, pressed && { opacity: 0.85 }]}
          hitSlop={8}
        >
          <MaterialCommunityIcons name="arrow-left" size={22} color={theme.colors.primary} />
          <Text style={styles.backRowText}>Back</Text>
        </Pressable>
        <Text style={styles.pageTitle}>Settings</Text>
        <Text style={styles.pageSub}>Manage your account preferences and security</Text>

        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <>
            <Text style={styles.secK}>Account</Text>
            <View style={styles.card}>
              <Row icon="email-outline" title="Email address" subtitle={me?.email ?? "—"} />
              <View style={styles.hair} />
              <Row
                icon="lock-outline"
                title="Change password"
                subtitle="Update via security settings"
                onPress={() => router.push("/security")}
              />
              <View style={styles.hair} />
              <View style={styles.row}>
                <View style={styles.rowIcon}>
                  <MaterialCommunityIcons name="shield-check-outline" size={22} color={theme.colors.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Two-factor authentication</Text>
                  <Text style={styles.rowSub}>Secure your account</Text>
                </View>
                <Switch value={twoFaOn} onValueChange={setTwoFaOn} trackColor={{ true: theme.colors.primary }} />
              </View>
            </View>

            <Text style={styles.secK}>Preferences</Text>
            <View style={styles.card}>
              <Text style={styles.innerK}>Currency</Text>
              <View style={styles.pillRow}>
                {CURRENCIES.map((c) => (
                  <Pressable key={c} style={[styles.pill, currency === c && styles.pillOn]} onPress={() => setCurrency(c)}>
                    <Text style={[styles.pillTxt, currency === c && styles.pillTxtOn]}>{c}</Text>
                  </Pressable>
                ))}
              </View>
              <Pressable style={styles.saveCurrency} onPress={saveCurrency} disabled={saving}>
                <Text style={styles.saveCurrencyTxt}>{saving ? "Saving…" : "Save currency"}</Text>
              </Pressable>
              <View style={styles.hair} />
              <Row icon="web" title="Language" subtitle="English (US)" />
              <View style={styles.hair} />
              <View style={styles.row}>
                <View style={styles.rowIcon}>
                  <MaterialCommunityIcons name="weather-night" size={22} color={theme.colors.secondary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Dark mode</Text>
                  <Text style={styles.rowSub}>Adaptive display theme</Text>
                </View>
                <Switch value={darkOn} onValueChange={setDarkOn} />
              </View>
            </View>

            <Text style={styles.secK}>Notifications</Text>
            <View style={styles.card}>
              <View style={styles.row}>
                <View style={[styles.rowIcon, { backgroundColor: theme.colors.tertiaryContainer }]}>
                  <MaterialCommunityIcons name="bell-outline" size={22} color={theme.colors.tertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Push notifications</Text>
                  <Text style={styles.rowSub}>Alerts on your device</Text>
                </View>
                <Switch value={pushOn} onValueChange={setPushOn} trackColor={{ true: theme.colors.primary }} />
              </View>
              <View style={styles.hair} />
              <View style={styles.row}>
                <View style={[styles.rowIcon, { backgroundColor: theme.colors.tertiaryContainer }]}>
                  <MaterialCommunityIcons name="at" size={22} color={theme.colors.tertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Email notifications</Text>
                  <Text style={styles.rowSub}>Weekly summaries</Text>
                </View>
                <Switch value={emailOn} onValueChange={setEmailOn} />
              </View>
            </View>

            <Text style={styles.secK}>Data & privacy</Text>
            <View style={styles.card}>
              <Row
                icon="download-outline"
                title="Export data"
                subtitle="Download your activity"
                onPress={() => router.push("/reports")}
              />
              <View style={styles.hair} />
              <Row
                icon="delete-outline"
                title="Delete account"
                subtitle="Permanently remove data"
                right={<MaterialCommunityIcons name="alert-outline" size={22} color={theme.colors.error} />}
              />
            </View>

            <View style={styles.card}>
              <Row
                icon="home-outline"
                title="Household"
                subtitle={settings?.active_household_id ? "Active household set" : "Personal workspace"}
                onPress={() => router.push("/household")}
              />
              <View style={styles.hair} />
              <Row
                icon="link-variant"
                title="Integrations"
                subtitle="Banks and calendars"
                onPress={() => router.push("/settings/integrations")}
              />
            </View>

            {VersionFooter}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  backRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    marginBottom: 12,
  },
  backRowText: { fontSize: 15, fontFamily: "Inter_700Bold", color: theme.colors.primary },
  scroll: { paddingHorizontal: theme.spacing.xl, paddingTop: 20 },
  pageTitle: { fontSize: 28, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, textAlign: "center" },
  pageSub: {
    textAlign: "center",
    marginTop: 6,
    marginBottom: 20,
    color: theme.colors.secondary,
    fontFamily: "Inter_400Regular",
  },
  secK: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    marginBottom: 10,
    marginTop: 8,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    overflow: "hidden",
    marginBottom: 14,
    ...theme.shadows.sm,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: theme.spacing.lg,
  },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  rowTitle: { fontSize: 15, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  rowSub: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.secondary, marginTop: 2 },
  hair: { height: 1, backgroundColor: theme.colors.surfaceContainerLow },
  innerK: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    marginLeft: theme.spacing.lg,
    marginTop: theme.spacing.lg,
    letterSpacing: 1,
  },
  pillRow: { flexDirection: "row", gap: 8, flexWrap: "wrap", paddingHorizontal: theme.spacing.lg, marginTop: 10 },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  pillOn: { borderColor: theme.colors.primary, backgroundColor: theme.colors.primaryFixed },
  pillTxt: { fontFamily: "Inter_700Bold", color: theme.colors.secondary },
  pillTxtOn: { color: theme.colors.primary },
  saveCurrency: {
    marginHorizontal: theme.spacing.lg,
    marginTop: 12,
    marginBottom: theme.spacing.lg,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    alignItems: "center",
  },
  saveCurrencyTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold" },
  error: { color: theme.colors.error, marginTop: 12 },
  version: {
    textAlign: "center",
    fontSize: 10,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.secondary,
    lineHeight: 16,
    marginTop: 8,
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
});
