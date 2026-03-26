import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Button, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type Goal = {
  goal_id: string;
  name: string;
  target_amount: number | string;
  target_currency?: string;
  target_date?: string | null;
  start_amount?: number | string;
};

type GoalProgress = {
  goal_id: string;
  current_amount: number | string;
  target_amount: number | string;
  monthly_contribution?: number | string | null;
  days_remaining?: number | null;
};

type ContributionsResponse = {
  contributions?: Array<{
    contribution_id?: string;
    amount?: number | string;
    contribution_date?: string;
    source?: string | null;
  }>;
};

function toNumber(v: unknown): number {
  const n = typeof v === "number" ? v : Number(String(v ?? 0));
  return Number.isFinite(n) ? n : 0;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

function fmtDateShort(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(String(iso).slice(0, 10) + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
  } catch {
    return fmtDate(iso);
  }
}

function toMonthsRemaining(days?: number | string | null): number | null {
  if (days === null || days === undefined) return null;
  const n = toNumber(days);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.max(0, Math.round(n / 30));
}

function goalIconFromName(name?: string) {
  const n = (name ?? "").toLowerCase();
  if (/(emergency|fund|rainy)/.test(n)) return { icon: "emergency" as any, tileBg: "#fee2e2", iconColor: "#dc2626" };
  if (/(vacation|europe|summer|travel|trip)/.test(n)) return { icon: "flight_takeoff" as any, tileBg: "#dbeafe", iconColor: "#2563eb" };
  if (/(car|vehicle|electric|ev|tesla)/.test(n)) return { icon: "directions_car" as any, tileBg: "#fef3c7", iconColor: "#b45309" };
  if (/(retire|retirement|pension|house|home)/.test(n)) return { icon: "home" as any, tileBg: theme.colors.primaryContainer, iconColor: theme.colors.primary };
  return { icon: "bank" as any, tileBg: theme.colors.surfaceContainer, iconColor: theme.colors.primary };
}

function contributionIconFromSource(source?: string | null) {
  const s = (source ?? "").toLowerCase();
  if (/(bonus|award)/.test(s)) return { icon: "star" as any, tileBg: "#fef3c7", iconColor: "#b45309" };
  if (/(auto|transfer|deposit)/.test(s)) return { icon: "trending-up" as any, tileBg: "#e0f2fe", iconColor: "#2563eb" };
  return { icon: "bank" as any, tileBg: theme.colors.surfaceContainer, iconColor: theme.colors.primary };
}

export default function GoalDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const goalId = params.goal_id ? String(params.goal_id) : "";

  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [goal, setGoal] = useState<Goal | null>(null);
  const [progress, setProgress] = useState<GoalProgress | null>(null);
  const [contribs, setContribs] = useState<ContributionsResponse["contributions"]>([]);

  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [contribOpen, setContribOpen] = useState(false);
  const [autoDepositOn, setAutoDepositOn] = useState(true);

  const pct = useMemo(() => {
    const cur = toNumber(progress?.current_amount ?? goal?.start_amount ?? 0);
    const tgt = toNumber(progress?.target_amount ?? goal?.target_amount ?? 0);
    return tgt > 0 ? Math.min(100, Math.round((cur / tgt) * 100)) : 0;
  }, [goal, progress]);

  const load = async () => {
    if (!goalId) throw new Error("Missing goal id.");
    const [gRes, pRes, cRes] = await Promise.all([
      authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}`, { method: "GET" }),
      authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/progress`, { method: "GET" }),
      authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/contributions`, { method: "GET" }),
    ]);
    const g = (await gRes.json().catch(() => null)) as Goal | null;
    const p = (await pRes.json().catch(() => null)) as GoalProgress | null;
    const c = (await cRes.json().catch(() => null)) as ContributionsResponse | null;
    return { g, p, c };
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const { g, p, c } = await load();
        if (cancelled) return;
        setGoal(g);
        setProgress(p);
        setContribs(Array.isArray(c?.contributions) ? c!.contributions : []);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load goal.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [goalId]);

  const addContribution = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: any = {
        amount: Number(amount),
      };
      if (!Number.isFinite(payload.amount) || payload.amount <= 0) {
        throw new Error("Amount must be a positive number.");
      }
      if (date.trim()) payload.contribution_date = date.trim().slice(0, 10);
      if (note.trim()) payload.source = note.trim();

      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/contributions`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(formatApiDetail(data?.detail, "Failed to add contribution."));

      // Reload progress + contributions
      const [pRes, cRes] = await Promise.all([
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/progress`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/contributions`, { method: "GET" }),
      ]);
      const p = (await pRes.json().catch(() => null)) as GoalProgress | null;
      const c = (await cRes.json().catch(() => null)) as ContributionsResponse | null;
      setProgress(p);
      setContribs(Array.isArray(c?.contributions) ? c!.contributions : []);
      setAmount("");
      setDate("");
      setNote("");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to add contribution.");
    } finally {
      setSubmitting(false);
    }
  };

  const currentAmount = useMemo(
    () => toNumber(progress?.current_amount ?? goal?.start_amount ?? 0),
    [goal, progress],
  );
  const targetAmount = useMemo(
    () => toNumber(progress?.target_amount ?? goal?.target_amount ?? 0),
    [goal, progress],
  );
  const monthsRemaining = useMemo(
    () => toMonthsRemaining(progress?.days_remaining ?? null),
    [progress?.days_remaining],
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.background }}>
      <View style={[styles.topBar, { paddingTop: insets.top + 10 }]}>
        <Pressable hitSlop={12} onPress={() => router.back()} style={styles.backHit}>
          <MaterialCommunityIcons name="arrow-left" size={26} color={theme.colors.primary} />
        </Pressable>
        <Text style={styles.topBrand}>pocketii</Text>
        <Pressable
          hitSlop={12}
          onPress={() => router.push("/notifications")}
          style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}
        >
          <MaterialCommunityIcons name="bell-outline" size={24} color={theme.colors.primary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + 40 }]}>
        {loading ? (
          <ActivityIndicator style={{ marginTop: 18 }} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : goal ? (
          <>
            <View style={styles.heroCard}>
              <View style={styles.heroHead}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.heroK}>Active Savings Goal</Text>
                  <Text style={styles.heroTitle}>{goal.name}</Text>
                </View>
                <Pressable onPress={() => setContribOpen(true)} style={styles.editBtn}>
                  <MaterialCommunityIcons name="pencil-outline" size={22} color={theme.colors.secondary} />
                </Pressable>
              </View>

              <View style={styles.ringWrap}>
                <View style={styles.ringBg} />
                <Text style={styles.ringPct}>{pct}%</Text>
                <Text style={styles.ringLbl}>Completed</Text>
              </View>

              <View style={styles.amountGrid}>
                <View style={styles.amountTileMuted}>
                  <Text style={styles.amountTileK}>Target Amount</Text>
                  <Text style={styles.amountTileV}>{fmtMoney(targetAmount)}</Text>
                </View>
                <View style={styles.amountTilePrimary}>
                  <Text style={[styles.amountTileK, { color: theme.colors.primary }]}>Current Balance</Text>
                  <Text style={[styles.amountTileV, { color: theme.colors.primary }]}>{fmtMoney(currentAmount)}</Text>
                </View>
              </View>
            </View>

            <View style={styles.timelineCard}>
              <View style={styles.timelineHead}>
              <MaterialCommunityIcons name="calendar" size={18} color={theme.colors.tertiary} />
                <Text style={styles.timelineK}>Timeline Status</Text>
              </View>
              <Text style={styles.timelineMonths}>{monthsRemaining === null ? "—" : `${monthsRemaining} months remaining`}</Text>
              <Text style={styles.timelineBody}>
                {monthsRemaining === null
                  ? "You're currently building your history. Contributions will update your schedule."
                  : "You're currently 2 weeks ahead of your projected schedule. Keep the momentum!"}
              </Text>
              <View style={styles.timelineBarTrack}>
                <View style={[styles.timelineBarFill, { width: `${pct}%` }]} />
              </View>
              <View style={styles.timelineDatesRow}>
                <Text style={styles.timelineDateTxt}>Started: —</Text>
                <Text style={styles.timelineDateTxt}>Target: {goal.target_date ? fmtDateShort(goal.target_date) : "—"}</Text>
              </View>
            </View>

            <View style={styles.bentoGrid}>
              <Pressable
                style={({ pressed }) => [styles.bentoPrimary, pressed && { opacity: 0.9 }]}
                onPress={() => setContribOpen(true)}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.bentoK}>Accelerate Goal</Text>
                  <Text style={styles.bentoTitle}>Make Contribution</Text>
                </View>
                <MaterialCommunityIcons name="plus-circle-outline" size={28} color={theme.colors.onPrimary} />
              </Pressable>

              <Pressable style={styles.bentoSecondary} onPress={() => setAutoDepositOn((v) => !v)}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.bentoKSecondary}>Smart Savings</Text>
                  <Text style={styles.bentoSecondaryTitle}>Auto-Deposit: {autoDepositOn ? "On" : "Off"}</Text>
                </View>
                <View
                  style={[
                    styles.switchMock,
                    autoDepositOn ? { justifyContent: "flex-end" } : { justifyContent: "flex-start" },
                  ]}
                >
                  <View style={styles.switchKnob} />
                </View>
              </Pressable>
            </View>

            <View style={styles.historyCard}>
              <View style={styles.historyHead}>
                <Text style={styles.historyTitle}>Contribution History</Text>
                <Pressable onPress={() => {}} hitSlop={8}>
                  <Text style={styles.viewAll}>View All</Text>
                </Pressable>
              </View>

              {contribs && contribs.length ? (
                <View>
                  {contribs.slice(0, 6).map((c, idx) => {
                    const meta = contributionIconFromSource(c.source ?? null);
                    const amt = fmtMoney(c.amount ?? 0);
                    const when = c.contribution_date ? fmtDateShort(c.contribution_date) : "—";
                    return (
                      <View
                        key={String(c.contribution_id ?? idx)}
                        style={[styles.historyItem, idx < Math.min(6, contribs.length) - 1 ? styles.historyDivider : null]}
                      >
                        <View style={[styles.historyIconTile, { backgroundColor: meta.tileBg }]}>
                          <MaterialCommunityIcons name={meta.icon as any} size={22} color={meta.iconColor} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.historyItemTitle}>{c.source ? c.source : "Contribution"}</Text>
                          <Text style={styles.historyItemMeta}>{when}</Text>
                        </View>
                        <View style={{ alignItems: "flex-end" }}>
                          <Text style={styles.historyAmt}>{amt}</Text>
                          <Text style={styles.historyProcessed}>Processed</Text>
                        </View>
                      </View>
                    );
                  })}
                </View>
              ) : (
                <Text style={styles.mutedText}>No contributions yet.</Text>
              )}
            </View>

            {contribOpen ? (
              <View style={styles.formCard}>
                <Text style={styles.formTitle}>Add Contribution</Text>

                <Text style={styles.label}>Amount</Text>
                <TextInput value={amount} onChangeText={setAmount} style={styles.input} keyboardType="decimal-pad" placeholder="0.00" />

                <Text style={[styles.label, { marginTop: 10 }]}>Date (optional)</Text>
                <TextInput value={date} onChangeText={setDate} style={styles.input} placeholder="YYYY-MM-DD" />

                <Text style={[styles.label, { marginTop: 10 }]}>Note (optional)</Text>
                <TextInput value={note} onChangeText={setNote} style={styles.input} placeholder="e.g. Monthly deposit" />

                {error ? <Text style={styles.errorTextInline}>{error}</Text> : null}

                <Pressable
                  style={({ pressed }) => [styles.primaryBtn, pressed && { opacity: 0.9 }]}
                  onPress={addContribution}
                  disabled={submitting}
                >
                  {submitting ? <ActivityIndicator color={theme.colors.onPrimary} /> : <Text style={styles.primaryBtnTxt}>Add Funds</Text>}
                </Pressable>
              </View>
            ) : null}

            <View style={styles.aiCard}>
              <View style={styles.aiIconWrap}>
                <MaterialCommunityIcons name="lightbulb" size={20} color={theme.colors.onPrimaryContainer} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.aiTitle}>pocketii insights</Text>
                <Text style={styles.aiBody}>
                  Based on your current spending habits, if you increase your monthly contribution by $450, you could reach your goal 3 months earlier than planned.
                </Text>
              </View>
            </View>
          </>
        ) : (
          <Text style={styles.mutedText}>No goal loaded.</Text>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 12,
    backgroundColor: theme.colors.surface,
  },
  backHit: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  topBrand: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },

  container: { padding: 20, gap: 16 },
  errorText: { color: theme.colors.error, marginTop: 12, fontFamily: "Inter_600SemiBold" },
  errorTextInline: { color: theme.colors.error, marginTop: 10, fontFamily: "Inter_600SemiBold" },
  mutedText: { color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular" },

  heroCard: {
    backgroundColor: theme.colors.surfaceContainerLowest,
    borderRadius: 22,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
  },
  heroHead: { flexDirection: "row", alignItems: "flex-start", gap: 10, marginBottom: 10 },
  heroK: { fontSize: 10, fontFamily: "Inter_800ExtraBold", letterSpacing: 1.2, textTransform: "uppercase", color: theme.colors.secondary },
  heroTitle: { fontSize: 24, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 6 },
  editBtn: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: theme.colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
  },

  ringWrap: {
    alignItems: "center",
    justifyContent: "center",
    height: 160,
    marginTop: 8,
  },
  ringBg: {
    position: "absolute",
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 12,
    borderColor: theme.colors.surfaceContainerHighest,
    backgroundColor: "transparent",
  },
  ringPct: { fontSize: 38, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  ringLbl: { fontSize: 10, fontFamily: "Inter_800ExtraBold", letterSpacing: 1.2, textTransform: "uppercase", color: theme.colors.secondary },

  amountGrid: { flexDirection: "row", gap: 10, marginTop: 6 },
  amountTileMuted: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    backgroundColor: theme.colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  amountTilePrimary: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    backgroundColor: `${theme.colors.primary}12`,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
  },
  amountTileK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    letterSpacing: 1.2,
    textTransform: "uppercase",
    color: theme.colors.secondary,
  },
  amountTileV: { marginTop: 6, fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },

  timelineCard: {
    backgroundColor: theme.colors.inverseSurface,
    borderRadius: 24,
    padding: 16,
    overflow: "hidden",
  },
  timelineHead: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 6 },
  timelineK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: "rgba(255,255,255,0.7)",
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  timelineMonths: { fontSize: 26, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimary, marginTop: 6 },
  timelineBody: {
    marginTop: 8,
    fontSize: 13,
    color: "rgba(255,255,255,0.6)",
    lineHeight: 18,
    fontFamily: "Inter_400Regular",
  },
  timelineBarTrack: { marginTop: 12, height: 10, backgroundColor: "rgba(255,255,255,0.12)", borderRadius: 999, overflow: "hidden" },
  timelineBarFill: { height: "100%", backgroundColor: theme.colors.tertiary },
  timelineDatesRow: { marginTop: 10, flexDirection: "row", justifyContent: "space-between" },
  timelineDateTxt: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: "rgba(255,255,255,0.4)",
    letterSpacing: 1.2,
    textTransform: "uppercase",
    flex: 1,
  },

  bentoGrid: { flexDirection: "row", gap: 10 },
  bentoPrimary: {
    flex: 1,
    backgroundColor: theme.colors.primary,
    borderRadius: 20,
    padding: 16,
    alignItems: "flex-start",
    justifyContent: "space-between",
    ...theme.shadows.md,
  },
  bentoSecondary: {
    flex: 1,
    backgroundColor: theme.colors.surfaceContainerHighest,
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  bentoK: { fontSize: 10, fontFamily: "Inter_800ExtraBold", letterSpacing: 1.4, textTransform: "uppercase", color: "rgba(255,255,255,0.7)" },
  bentoTitle: { marginTop: 6, fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimary },
  bentoKSecondary: { fontSize: 10, fontFamily: "Inter_800ExtraBold", letterSpacing: 1.4, textTransform: "uppercase", color: theme.colors.secondary },
  bentoSecondaryTitle: { marginTop: 6, fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },

  switchMock: { width: 44, height: 24, borderRadius: 999, backgroundColor: theme.colors.primary, padding: 2, alignItems: "flex-start" },
  switchKnob: { width: 18, height: 18, backgroundColor: theme.colors.surface, borderRadius: 999 },

  historyCard: {
    backgroundColor: theme.colors.surfaceContainerLowest,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    overflow: "hidden",
  },
  historyHead: {
    padding: 16,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  historyTitle: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  viewAll: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.primary, letterSpacing: 0.2 },
  historyItem: { padding: 16, flexDirection: "row", gap: 12, alignItems: "center" },
  historyDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.outlineVariant },
  historyIconTile: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  historyItemTitle: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  historyItemMeta: { marginTop: 2, fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.onSurfaceVariant },
  historyAmt: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  historyProcessed: {
    marginTop: 4,
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },

  formCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    padding: 16,
  },
  formTitle: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginBottom: 8 },
  label: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurfaceVariant, marginTop: 6 },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: theme.colors.surfaceContainerLowest,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
  },
  primaryBtn: {
    marginTop: 14,
    backgroundColor: theme.colors.primary,
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: "center",
    ...theme.shadows.sm,
  },
  primaryBtnTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 16 },

  aiCard: {
    backgroundColor: `${theme.colors.primaryContainer}CC`,
    borderRadius: 24,
    padding: 16,
    flexDirection: "row",
    gap: 12,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    marginTop: 4,
  },
  aiIconWrap: {
    width: 44,
    height: 44,
    borderRadius: 16,
    backgroundColor: theme.colors.surface,
    alignItems: "center",
    justifyContent: "center",
    ...theme.shadows.sm,
  },
  aiTitle: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimaryContainer, marginTop: 2 },
  aiBody: { marginTop: 6, fontSize: 13, color: `${theme.colors.onPrimaryContainer}CC`, lineHeight: 18, fontFamily: "Inter_400Regular" },
});

