import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Modal,
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
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { clearTokens } from "../../src/authTokens";
import { AppTheme, theme, useAppTheme } from "../../src/theme";
import { agentLog } from "../../src/debug/agentLog";
import { formatApiDetail } from "../../src/formatApiDetail";

type MeResponse = {
  email?: string;
  first_name?: string | null;
  last_name?: string | null;
  bio?: string | null;
  created_at?: string | null;
  name?: string | null;
  email_verified_at?: string | null;
};

type PortfolioValueResponse = {
  total_market_value?: number | string;
};

type HealthResponse = {
  score?: number;
  headline?: string;
};

type SyncSummary = {
  plaid_items?: number;
  teller_enrollments?: number;
  bank_linked?: boolean;
};

function fmtMemberSince(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", year: "numeric" });
  } catch {
    return "—";
  }
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function ProfileScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const currentTheme = useAppTheme();
  const styles = useMemo(() => createStyles(currentTheme), [currentTheme]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioValueResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [syncSummary, setSyncSummary] = useState<SyncSummary | null>(null);

  const [personalOpen, setPersonalOpen] = useState(false);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [meRes, portRes, healthRes, syncRes] = await Promise.all([
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/user/me`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/value`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/health`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/sync-status`, { method: "GET" }),
      ]);

      const meJson = await meRes.json().catch(() => null);
      agentLog({
        hypothesisId: "H5-H8",
        location: "profile.tsx:load",
        message: "profile parallel GET statuses",
        data: {
          meStatus: meRes.status,
          meOk: meRes.ok,
          portStatus: portRes.status,
          healthStatus: healthRes.status,
          syncStatus: syncRes.status,
          meDetailJson: meJson
            ? JSON.stringify((meJson as { detail?: unknown }).detail ?? meJson).slice(0, 600)
            : null,
        },
      });
      if (!meRes.ok) {
        throw new Error(formatApiDetail((meJson as any)?.detail, "Failed to load profile."));
      }
      setMe(meJson as MeResponse);
      setFirstName((meJson as MeResponse)?.first_name ?? "");
      setLastName((meJson as MeResponse)?.last_name ?? "");
      setBio((meJson as MeResponse)?.bio ?? "");

      const portJson = portRes.ok ? ((await portRes.json().catch(() => null)) as PortfolioValueResponse) : null;
      setPortfolio(portJson);

      const healthJson = healthRes.ok ? ((await healthRes.json().catch(() => null)) as HealthResponse) : null;
      setHealth(healthJson);

      const syncJson = syncRes.ok ? ((await syncRes.json().catch(() => null)) as SyncSummary) : null;
      setSyncSummary(syncJson);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load profile.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const displayName = useMemo(() => {
    const m = me;
    if (!m) return "User";
    const n = [m.first_name, m.last_name].filter(Boolean).join(" ").trim();
    return n || m.name?.trim() || m.email || "User";
  }, [me]);

  const linkedCount =
    (syncSummary?.plaid_items ?? 0) + (syncSummary?.teller_enrollments ?? 0);
  const linkedLabel =
    linkedCount === 1 ? "1 connection" : `${linkedCount} connections`;

  const healthScore = health?.score;
  const healthDisplay =
    typeof healthScore === "number" && Number.isFinite(healthScore)
      ? `${Math.round(healthScore)}/100`
      : "—";

  const isVerified = Boolean(me?.email_verified_at);

  const saveProfile = async () => {
    setSaving(true);
    setError(null);
    try {
      const url = `${GATEWAY_BASE_URL}/user/me`;
      const payload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        bio: bio.trim(),
      };
      const res = await authClient.requestWithRefresh(url, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail(data?.detail, "Failed to save."));
      }
      setMe(data as MeResponse);
      setPersonalOpen(false);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    await clearTokens();
    router.replace("/login");
  };

  const SettingsRow = ({
    icon,
    title,
    subtitle,
    onPress,
  }: {
    icon: keyof typeof MaterialCommunityIcons.glyphMap;
    title: string;
    subtitle: string;
    onPress: () => void;
  }) => (
    <Pressable style={({ pressed }) => [styles.settingsRow, pressed && { opacity: 0.92 }]} onPress={onPress}>
      <View style={styles.settingsRowInner}>
        <View style={styles.settingsIcon}>
          <MaterialCommunityIcons name={icon} size={22} color={currentTheme.colors.secondary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.settingsTitle}>{title}</Text>
          <Text style={styles.settingsSub}>{subtitle}</Text>
        </View>
        <MaterialCommunityIcons name="chevron-right" size={22} color={currentTheme.colors.secondaryFixedDim} />
      </View>
    </Pressable>
  );

  return (
    <View style={[styles.root, { backgroundColor: currentTheme.colors.background }]}> 
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 100 },
        ]}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.profileMenuOnly}>
          <Pressable
            onPress={() => router.push("/more")}
            hitSlop={12}
            accessibilityRole="button"
            accessibilityLabel="Open menu"
          >
            <MaterialCommunityIcons name="menu" size={26} color={currentTheme.colors.primary} />
          </Pressable>
        </View>
        {loading ? (
          <ActivityIndicator style={{ marginTop: 32 }} color={currentTheme.colors.primary} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : me ? (
          <>
            <View style={styles.heroCard}>
              <View style={styles.heroGlow} />
              <View style={{ zIndex: 1 }}>
                <View style={styles.badge}>
                  <Text style={styles.badgeText}>Member</Text>
                </View>
                <Text style={styles.heroName}>{displayName}</Text>
                <Text style={styles.heroEmail}>{me.email ?? ""}</Text>
              </View>
              <View style={styles.heroStats}>
                <View style={styles.statBox}>
                  <Text style={styles.statLabel}>Member since</Text>
                  <Text style={styles.statValue}>{fmtMemberSince(me.created_at)}</Text>
                </View>
                <View style={styles.statBox}>
                  <Text style={styles.statLabel}>Linked banks</Text>
                  <Text style={[styles.statValue, { color: currentTheme.colors.inversePrimary }]}> 
                    {linkedLabel}
                  </Text>
                </View>
              </View>
            </View>

            <View style={styles.statGrid}>
              <View style={styles.statCard}>
                <MaterialCommunityIcons name="wallet-outline" size={36} color={currentTheme.colors.primary} />
                <Text style={styles.statCardValue}>{fmtMoney(portfolio?.total_market_value)}</Text>
                <Text style={styles.statCardLabel}>Total Portfolio Value</Text>
              </View>
              <View style={styles.statCard}>
                <MaterialCommunityIcons name="flash-outline" size={36} color={currentTheme.colors.tertiary} />
                <Text style={styles.statCardValue}>{healthDisplay}</Text>
                <Text style={styles.statCardLabel}>Financial Health Score</Text>
              </View>
            </View>

            {isVerified ? (
              <View style={styles.verifyBanner}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.verifyTitle}>Identity verified</Text>
                  <Text style={styles.verifyBody}>
                    Your account meets email verification requirements for connected data.
                  </Text>
                </View>
                <View style={styles.verifyIcon}>
                  <MaterialCommunityIcons name="check-decagram" size={36} color={currentTheme.colors.primary} />
                </View>
              </View>
            ) : (
              <Pressable style={styles.verifyBannerUnset} onPress={() => router.push("/verify-email")}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.verifyTitleUnset}>Verify your email</Text>
                  <Text style={styles.verifyBodyUnset}>
                    Confirm your inbox so bank linking and sensitive actions stay protected.
                  </Text>
                </View>
                <MaterialCommunityIcons name="chevron-right" size={24} color={currentTheme.colors.primary} />
              </Pressable>
            )}

            <Text style={styles.sectionKicker}>Account Settings</Text>
            <View style={styles.settingsCard}>
              <SettingsRow
                icon="account-outline"
                title="Personal Information"
                subtitle="Update your details and contact information"
                onPress={() => setPersonalOpen(true)}
              />
              <View style={styles.settingsDivider} />
              <SettingsRow
                icon="credit-card-outline"
                title="Payment Methods"
                subtitle="Manage cards and billing preferences"
                onPress={() => router.push("/settings")}
              />
              <View style={styles.settingsDivider} />
              <SettingsRow
                icon="bank-outline"
                title="Linked Banks"
                subtitle={`Manage your ${linkedCount || "0"} bank connections`}
                onPress={() => router.push("/settings/integrations")}
              />
              <View style={styles.settingsDivider} />
              <SettingsRow
                icon="shield-outline"
                title="Security"
                subtitle="Two-factor authentication and access logs"
                onPress={() => router.push("/security")}
              />
              <View style={styles.settingsDivider} />
              <SettingsRow
                icon="help-circle-outline"
                title="Help & Support"
                subtitle="Browse tools and documentation"
                onPress={() => router.push("/more")}
              />
            </View>

            <Pressable style={styles.logoutBtn} onPress={logout}>
              <MaterialCommunityIcons name="logout" size={22} color={currentTheme.colors.error} />
              <Text style={styles.logoutText}>Log Out</Text>
            </Pressable>
          </>
        ) : (
          <Text style={styles.muted}>No profile loaded.</Text>
        )}
      </ScrollView>

      <Modal visible={personalOpen} animationType="slide" transparent>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { paddingBottom: insets.bottom + 16 }]}>
            <Text style={styles.modalTitle}>Personal information</Text>
            <Text style={styles.label}>First name</Text>
            <TextInput value={firstName} onChangeText={setFirstName} style={styles.input} />
            <Text style={[styles.label, { marginTop: 12 }]}>Last name</Text>
            <TextInput value={lastName} onChangeText={setLastName} style={styles.input} />
            <Text style={[styles.label, { marginTop: 12 }]}>Bio</Text>
            <TextInput
              value={bio}
              onChangeText={setBio}
              style={[styles.input, { minHeight: 72 }]}
              multiline
            />
            {error ? <Text style={styles.errorText}>{error}</Text> : null}
            <Pressable style={styles.primaryBtn} onPress={saveProfile} disabled={saving}>
              <Text style={styles.primaryBtnText}>{saving ? "Saving…" : "Save"}</Text>
            </Pressable>
            <Pressable onPress={() => setPersonalOpen(false)}>
              <Text style={styles.cancelLink}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  root: { flex: 1 },
  profileMenuOnly: {
    alignSelf: "flex-start",
    marginBottom: 8,
  },
  scroll: { paddingHorizontal: theme.spacing.xl },
  heroCard: {
    backgroundColor: theme.colors.inverseSurface,
    borderRadius: theme.radii.xl + 4,
    padding: theme.spacing.xxl,
    overflow: "hidden",
    marginBottom: 20,
  },
  heroGlow: {
    position: "absolute",
    top: -40,
    right: -40,
    width: 160,
    height: 160,
    borderRadius: 80,
    backgroundColor: theme.colors.primary,
    opacity: 0.2,
  },
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(37,99,235,0.25)",
    borderWidth: 1,
    borderColor: "rgba(96,165,250,0.35)",
    marginBottom: 16,
  },
  badgeText: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.inversePrimary,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  heroName: {
    fontSize: 32,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
    letterSpacing: -0.5,
  },
  heroEmail: {
    marginTop: 6,
    fontSize: 15,
    fontFamily: "Inter_500Medium",
    color: "rgba(241,245,249,0.7)",
  },
  heroStats: {
    flexDirection: "row",
    gap: 12,
    marginTop: 28,
  },
  statBox: {
    flex: 1,
    padding: 16,
    borderRadius: theme.radii.lg,
    backgroundColor: "rgba(255,255,255,0.06)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  statLabel: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: "rgba(148,163,184,0.95)",
    letterSpacing: 1.8,
    textTransform: "uppercase",
    marginBottom: 6,
  },
  statValue: {
    fontSize: 17,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
  },
  statGrid: { flexDirection: "row", gap: 12, marginBottom: 16 },
  statCard: {
    flex: 1,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.xl,
    padding: theme.spacing.xl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
    gap: 8,
  },
  statCardValue: {
    fontSize: 22,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginTop: 4,
  },
  statCardLabel: {
    fontSize: 13,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
  },
  verifyBannerUnset: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.primaryContainer,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}33`,
    marginBottom: 8,
  },
  verifyTitleUnset: { fontSize: 15, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  verifyBodyUnset: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.onSurfaceVariant, marginTop: 4 },
  verifyBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.primaryContainer,
    borderRadius: theme.radii.xl,
    padding: theme.spacing.xl,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}18`,
    marginBottom: 24,
    gap: 12,
  },
  verifyTitle: {
    fontSize: 17,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimaryContainer,
  },
  verifyBody: {
    marginTop: 4,
    fontSize: 13,
    fontFamily: "Inter_400Regular",
    color: `${theme.colors.onPrimaryContainer}bb`,
  },
  verifyIcon: { marginLeft: 4 },
  sectionKicker: {
    fontSize: 12,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    textTransform: "uppercase",
    marginBottom: 12,
  },
  settingsCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.xl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    overflow: "hidden",
    ...theme.shadows.sm,
    marginBottom: 20,
  },
  settingsRow: { backgroundColor: theme.colors.surface },
  settingsRowInner: {
    flexDirection: "row",
    alignItems: "center",
    padding: theme.spacing.xl,
    gap: 14,
  },
  settingsIcon: {
    width: 48,
    height: 48,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  settingsTitle: { fontSize: 16, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  settingsSub: {
    fontSize: 13,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    marginTop: 2,
  },
  settingsDivider: { height: 1, backgroundColor: theme.colors.surfaceContainerLow },
  logoutBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 16,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.surface,
    marginBottom: 24,
  },
  logoutText: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.error },
  muted: { color: theme.colors.onSurfaceVariant },
  errorText: { color: theme.colors.error, marginTop: 8, fontFamily: "Inter_600SemiBold" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(15,23,42,0.45)",
    justifyContent: "flex-end",
  },
  modalCard: {
    backgroundColor: theme.colors.surface,
    borderTopLeftRadius: theme.radii.xl,
    borderTopRightRadius: theme.radii.xl,
    padding: theme.spacing.xxl,
  },
  modalTitle: {
    fontSize: 20,
    fontFamily: "Inter_800ExtraBold",
    marginBottom: 16,
    color: theme.colors.onSurface,
  },
  label: {
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: theme.radii.md,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
    backgroundColor: theme.colors.surfaceContainerLow,
  },
  primaryBtn: {
    marginTop: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    alignItems: "center",
    ...theme.shadows.sm,
  },
  primaryBtnText: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 16 },
  cancelLink: {
    textAlign: "center",
    marginTop: 14,
    color: theme.colors.secondary,
    fontFamily: "Inter_600SemiBold",
  },
});
