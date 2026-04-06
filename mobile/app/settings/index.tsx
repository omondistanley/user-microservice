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
import { AppTheme, ThemePreference, useAppTheme, useThemePreference } from "../../src/theme";

type SettingsResponse = {
  default_currency?: string;
  theme_preference?: ThemePreference;
  push_notifications_enabled?: boolean;
  email_notifications_enabled?: boolean;
  active_household_id?: string | null;
};

type Me = { email?: string };

const CURRENCIES = ["USD", "EUR", "GBP"] as const;
const APPEARANCE_OPTIONS: ThemePreference[] = ["light", "system", "dark"];
type Currency = (typeof CURRENCIES)[number];

export default function SettingsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const theme = useAppTheme();
  const { preference, resolvedMode, setPreference } = useThemePreference();
  const styles = useMemo(() => createStyles(theme), [theme]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [currency, setCurrency] = useState<Currency>("USD");
  const [savingCurrency, setSavingCurrency] = useState(false);
  const [savingAppearance, setSavingAppearance] = useState(false);
  const [savingPush, setSavingPush] = useState(false);
  const [savingEmail, setSavingEmail] = useState(false);
  const [pushOn, setPushOn] = useState(true);
  const [emailOn, setEmailOn] = useState(false);

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
      const nextCurrency = String(s?.default_currency ?? "USD").toUpperCase();
      if ((CURRENCIES as readonly string[]).includes(nextCurrency)) setCurrency(nextCurrency as Currency);
      setPushOn(Boolean(s?.push_notifications_enabled ?? true));
      setEmailOn(Boolean(s?.email_notifications_enabled ?? false));
      if (s?.theme_preference && APPEARANCE_OPTIONS.includes(s.theme_preference)) {
        await setPreference(s.theme_preference);
      }
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const patchSettings = async (patch: Partial<SettingsResponse>) => {
    const json = await authClient.requestJsonWithRefresh<SettingsResponse>(`${GATEWAY_BASE_URL}/api/v1/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    setSettings(json);
    return json;
  };

  const saveCurrency = async () => {
    setSavingCurrency(true);
    setError(null);
    try {
      await patchSettings({ default_currency: currency });
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to save currency.");
    } finally {
      setSavingCurrency(false);
    }
  };

  const changeAppearance = async (nextPreference: ThemePreference) => {
    if (nextPreference === preference) return;
    const previous = preference;
    setSavingAppearance(true);
    setError(null);
    await setPreference(nextPreference);
    try {
      await patchSettings({ theme_preference: nextPreference });
    } catch (e: any) {
      await setPreference(previous);
      setError(e?.message ? String(e.message) : "Failed to save theme preference.");
    } finally {
      setSavingAppearance(false);
    }
  };

  const changePushPreference = async (nextValue: boolean) => {
    const previous = pushOn;
    setPushOn(nextValue);
    setSavingPush(true);
    setError(null);
    try {
      await patchSettings({ push_notifications_enabled: nextValue });
    } catch (e: any) {
      setPushOn(previous);
      setError(e?.message ? String(e.message) : "Failed to save push notification preference.");
    } finally {
      setSavingPush(false);
    }
  };

  const changeEmailPreference = async (nextValue: boolean) => {
    const previous = emailOn;
    setEmailOn(nextValue);
    setSavingEmail(true);
    setError(null);
    try {
      await patchSettings({ email_notifications_enabled: nextValue });
    } catch (e: any) {
      setEmailOn(previous);
      setError(e?.message ? String(e.message) : "Failed to save email notification preference.");
    } finally {
      setSavingEmail(false);
    }
  };

  const VersionFooter = useMemo(
    () => (
      <Text style={styles.version}>
        pocketii v3.4.2 (production){"\n"}© 2025 pocketii
      </Text>
    ),
    [styles.version],
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

  const appearanceSubtitle =
    preference === "system" ? `Following device setting (${resolvedMode})` : `Always ${preference}`;

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
          <ActivityIndicator style={{ marginTop: 24 }} color={theme.colors.primary} />
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
              <Row
                icon="shield-check-outline"
                title="Two-factor authentication"
                subtitle="TOTP enrollment is planned. Open Security for the current status."
                onPress={() => router.push("/security")}
              />
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
              <Pressable style={styles.saveButton} onPress={saveCurrency} disabled={savingCurrency}>
                <Text style={styles.saveButtonTxt}>{savingCurrency ? "Saving…" : "Save currency"}</Text>
              </Pressable>
              <View style={styles.hair} />
              <Row icon="web" title="Language" subtitle="English (US)" />
              <View style={styles.hair} />
              <View style={styles.preferenceBlock}>
                <View style={styles.preferenceHeader}>
                  <View style={styles.rowIcon}>
                    <MaterialCommunityIcons name="theme-light-dark" size={22} color={theme.colors.secondary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>Appearance</Text>
                    <Text style={styles.rowSub}>{appearanceSubtitle}</Text>
                  </View>
                  {savingAppearance ? <ActivityIndicator size="small" color={theme.colors.primary} /> : null}
                </View>
                <View style={styles.segmentRow}>
                  {APPEARANCE_OPTIONS.map((option) => (
                    <Pressable
                      key={option}
                      style={[styles.segment, preference === option && styles.segmentOn]}
                      onPress={() => changeAppearance(option)}
                    >
                      <Text style={[styles.segmentTxt, preference === option && styles.segmentTxtOn]}>{option}</Text>
                    </Pressable>
                  ))}
                </View>
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
                  <Text style={styles.rowSub}>Stored as your in-app delivery preference.</Text>
                </View>
                {savingPush ? (
                  <ActivityIndicator size="small" color={theme.colors.primary} />
                ) : (
                  <Switch value={pushOn} onValueChange={changePushPreference} trackColor={{ true: theme.colors.primary }} />
                )}
              </View>
              <View style={styles.hair} />
              <View style={styles.row}>
                <View style={[styles.rowIcon, { backgroundColor: theme.colors.tertiaryContainer }]}>
                  <MaterialCommunityIcons name="at" size={22} color={theme.colors.tertiary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Email notifications</Text>
                  <Text style={styles.rowSub}>Stored as your weekly summary preference.</Text>
                </View>
                {savingEmail ? (
                  <ActivityIndicator size="small" color={theme.colors.primary} />
                ) : (
                  <Switch value={emailOn} onValueChange={changeEmailPreference} trackColor={{ true: theme.colors.primary }} />
                )}
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

const createStyles = (theme: AppTheme) => StyleSheet.create({
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
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1.5,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: "transparent",
  },
  pillOn: { borderColor: theme.colors.primary, backgroundColor: theme.colors.primary },
  pillTxt: { fontFamily: "Inter_700Bold", fontSize: 12, color: theme.colors.secondary, textTransform: "uppercase", letterSpacing: 0.5 },
  pillTxtOn: { color: "#fff" },
  saveButton: {
    marginHorizontal: theme.spacing.lg,
    marginTop: 12,
    marginBottom: theme.spacing.lg,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    alignItems: "center",
  },
  saveButtonTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold" },
  preferenceBlock: {
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.lg,
    gap: 12,
  },
  preferenceHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  segmentRow: {
    flexDirection: "row",
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: 999,
    padding: 4,
    gap: 6,
  },
  segment: {
    flex: 1,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 10,
  },
  segmentOn: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  segmentTxt: {
    color: theme.colors.secondary,
    fontFamily: "Inter_700Bold",
    textTransform: "uppercase",
    fontSize: 12,
  },
  segmentTxtOn: { color: theme.colors.onSurface },
  error: { color: theme.colors.error, marginTop: 12, fontFamily: "Inter_600SemiBold" },
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
