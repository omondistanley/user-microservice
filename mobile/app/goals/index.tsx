import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type Goal = {
  goal_id: string;
  name: string;
  target_amount: number | string;
  target_currency?: string;
  target_date?: string | null;
  start_amount?: number | string;
  is_active?: boolean;
};

type GoalProgress = {
  goal_id: string;
  current_amount: number | string;
  target_amount: number | string;
};

function toNumber(v: unknown): number {
  const n = typeof v === "number" ? v : Number(String(v ?? 0));
  return Number.isFinite(n) ? n : 0;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDateShort(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(String(iso).slice(0, 10) + "T12:00:00");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
  } catch {
    return String(iso).slice(0, 10);
  }
}

function goalStatusFromPct(pct: number) {
  // Matches the "On Track" vs "Below Pace" visual intent from v2 designs.
  const onTrack = pct >= 60;
  return {
    label: onTrack ? "On Track" : "Below Pace",
    bg: onTrack ? "#dcfce7" : "#fef3c7",
    fg: onTrack ? "#166534" : "#b45309",
    bar: onTrack ? theme.colors.primary : theme.colors.tertiary,
  };
}

function goalIconFromName(name?: string) {
  const n = (name ?? "").toLowerCase();
  if (/(emergency|fund|rainy)/.test(n)) {
    return { icon: "emergency", tileBg: "#fee2e2", iconColor: "#dc2626" as string };
  }
  if (/(vacation|europe|summer|travel|trip)/.test(n)) {
    return { icon: "flight_takeoff", tileBg: "#dbeafe", iconColor: "#2563eb" as string };
  }
  if (/(car|vehicle|electric|ev|tesla)/.test(n)) {
    return { icon: "directions_car", tileBg: "#fef3c7", iconColor: "#b45309" as string };
  }
  if (/(retire|retirement|pension|house|home)/.test(n)) {
    return { icon: "home", tileBg: theme.colors.primaryContainer, iconColor: theme.colors.primary };
  }
  if (/(education|school|learn)/.test(n)) {
    return { icon: "school", tileBg: "#eef2ff", iconColor: "#4f46e5" as string };
  }
  return { icon: "bank", tileBg: theme.colors.surfaceContainer, iconColor: theme.colors.primary };
}

export default function GoalsListScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [progressById, setProgressById] = useState<Map<string, GoalProgress>>(new Map());

  const totals = useMemo(() => {
    let totalSaved = 0;
    let totalTarget = 0;
    for (const g of goals) {
      const p = progressById.get(g.goal_id);
      const current = p ? toNumber(p.current_amount) : toNumber(g.start_amount);
      totalSaved += current;
      totalTarget += toNumber(g.target_amount);
    }
    const pct = totalTarget > 0 ? Math.round((totalSaved / totalTarget) * 100) : 0;
    return { totalSaved, totalTarget, pct, count: goals.length };
  }, [goals, progressById]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const listRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals?page=1&page_size=50`, {
          method: "GET",
        });
        const listData = await listRes.json().catch(() => null);
        const items = Array.isArray(listData?.items) ? (listData.items as Goal[]) : [];

        const progEntries = await Promise.all(
          items.map(async (g) => {
            try {
              const res = await authClient.requestWithRefresh(
                `${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(g.goal_id)}/progress`,
                { method: "GET" },
              );
              const data = await res.json().catch(() => null);
              return [g.goal_id, data as GoalProgress] as const;
            } catch {
              return [g.goal_id, { goal_id: g.goal_id, current_amount: g.start_amount ?? 0, target_amount: g.target_amount } as GoalProgress] as const;
            }
          }),
        );

        if (cancelled) return;
        setGoals(items);
        setProgressById(new Map(progEntries));
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load goals.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <MaterialCommunityIcons name="bank" size={26} color={theme.colors.primary} />
          <Text style={styles.title}>Indigo Vault</Text>
        </View>
        <Pressable onPress={() => router.push("/notifications")} style={styles.headerRightBtn}>
          <MaterialCommunityIcons name="bell-outline" size={24} color={theme.colors.primary} />
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <>
          <View style={styles.heroCard}>
            <View style={styles.heroBlob} />
            <Text style={styles.heroK}>Total Accumulated Savings</Text>
            <Text style={styles.heroAmt}>{fmtMoney(totals.totalSaved)}</Text>
            <View style={styles.heroTrendRow}>
              <MaterialCommunityIcons name="trending-up" size={16} color="#dbeafe" />
              <Text style={styles.heroTrendTxt}>+12.5% from last month</Text>
            </View>

            <View style={styles.heroBtnRow}>
              <Pressable style={styles.heroBtnOutline} onPress={() => router.push("/goals/add")}>
                <Text style={styles.heroBtnOutlineTxt}>Add New Goal</Text>
              </Pressable>
              <Pressable style={styles.heroBtnFill} onPress={() => router.push("/analytics")}>
                <Text style={styles.heroBtnFillTxt}>View Analytics</Text>
              </Pressable>
            </View>
          </View>

          <Text style={styles.activeTitle}>Active Savings Goals</Text>

          <View style={{ gap: 10 }}>
            {goals.length ? (
              goals.map((g) => {
                const p = progressById.get(g.goal_id);
                const current = p ? toNumber(p.current_amount) : toNumber(g.start_amount);
                const target = toNumber(g.target_amount);
                const pct = target > 0 ? Math.min(100, Math.round((current / target) * 100)) : 0;
                const left = target - current;
                const leftText = left <= 0 ? "Target reached" : `${fmtMoney(left)} to go`;
                const status = goalStatusFromPct(pct);
                const iconMeta = goalIconFromName(g.name);

                return (
                  <Pressable
                    key={g.goal_id}
                    style={styles.goalCard}
                    onPress={() => router.push(`/goals/${encodeURIComponent(g.goal_id)}`)}
                  >
                    <View style={styles.goalTop}>
                      <View style={[styles.goalIconTile, { backgroundColor: iconMeta.tileBg }]}>
                        <MaterialCommunityIcons name={iconMeta.icon as any} size={22} color={iconMeta.iconColor} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.goalName} numberOfLines={1}>
                          {g.name}
                        </Text>
                        <Text style={styles.goalTargetDate}>
                          Target Date: {fmtDateShort(g.target_date ?? null)}
                        </Text>
                      </View>
                      <View style={[styles.statusPill, { backgroundColor: status.bg }]}>
                        <Text style={[styles.statusPillTxt, { color: status.fg }]}>{status.label}</Text>
                        <Text style={[styles.statusPillPct, { color: status.fg }]}>{pct}%</Text>
                      </View>
                    </View>
                    <View style={styles.goalAmounts}>
                      <Text style={styles.goalCurrent}>{fmtMoney(current)}</Text>
                      <Text style={styles.goalTarget}>of {fmtMoney(target)}</Text>
                    </View>
                    <View style={styles.progressOuter}>
                      <View style={[styles.progressInner, { width: `${pct}%`, backgroundColor: status.bar }]} />
                    </View>
                    <Text style={styles.goalLeft}>{leftText}</Text>
                  </Pressable>
                );
              })
            ) : (
              <Text style={styles.mutedText}>No goals yet. Add one to get started.</Text>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: theme.colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 6,
  },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  title: { fontSize: 20, fontWeight: "900", color: theme.colors.primary },
  headerRightBtn: {
    width: 44,
    height: 44,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.surfaceContainer,
  },
  errorText: { color: "#dc2626" },
  mutedText: { color: "#64748b" },
  heroCard: {
    position: "relative",
    backgroundColor: theme.colors.primary,
    borderRadius: 18,
    padding: 16,
    overflow: "hidden",
    ...theme.shadows.md,
  },
  heroBlob: {
    position: "absolute",
    right: -60,
    top: -60,
    width: 140,
    height: 140,
    backgroundColor: `${theme.colors.primary}22`,
    borderRadius: 70,
  },
  heroK: { fontSize: 10, fontWeight: "900", color: "#bfdbfe", letterSpacing: 1.4, textTransform: "uppercase" },
  heroAmt: { fontSize: 34, fontWeight: "900", color: theme.colors.onPrimary, marginTop: 6 },
  heroTrendRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  heroTrendTxt: { fontSize: 13, fontFamily: "Inter_700Bold", color: "#dbeafe" },
  heroBtnRow: { flexDirection: "row", gap: 10, marginTop: 12 },
  heroBtnOutline: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: "center",
  },
  heroBtnOutlineTxt: { fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  heroBtnFill: {
    flex: 1,
    borderRadius: 14,
    paddingVertical: 12,
    borderWidth: 1,
    borderColor: "#dbeafe",
    backgroundColor: `${theme.colors.primary}15`,
    alignItems: "center",
  },
  heroBtnFillTxt: { fontFamily: "Inter_800ExtraBold", color: "#fff", textTransform: "uppercase", fontSize: 12 },
  activeTitle: { marginTop: 2, fontSize: 24, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  progressOuter: { height: 10, borderRadius: 999, backgroundColor: theme.colors.outlineVariant, overflow: "hidden" },
  progressInner: { height: "100%", borderRadius: 999, backgroundColor: theme.colors.primary },
  goalCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 16,
    padding: 14,
    gap: 10,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  goalTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12 },
  goalIconTile: { width: 44, height: 44, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  goalName: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  goalTargetDate: { marginTop: 4, fontSize: 12, fontFamily: "Inter_500Medium", color: theme.colors.onSurfaceVariant },
  statusPill: { paddingVertical: 8, paddingHorizontal: 10, borderRadius: 999, alignItems: "center", justifyContent: "center" },
  statusPillTxt: { fontSize: 10, fontFamily: "Inter_800ExtraBold" },
  statusPillPct: { fontSize: 12, fontFamily: "Inter_800ExtraBold" },
  goalAmounts: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  goalCurrent: { fontSize: 18, fontWeight: "900", color: "#0f172a" },
  goalTarget: { fontSize: 12, color: "#64748b", fontWeight: "800" },
  goalLeft: { fontSize: 12, color: "#334155", fontWeight: "700" },
});

