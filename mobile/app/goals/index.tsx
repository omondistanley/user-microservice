import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ExpandableCard } from "../../src/components/ui/ExpandableCard";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { formatApiDetail } from "../../src/formatApiDetail";

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
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editTarget, setEditTarget] = useState("");
  const [editTargetDate, setEditTargetDate] = useState("");
  const [rowBusy, setRowBusy] = useState(false);
  const [contribAmt, setContribAmt] = useState("");
  const [contribBusy, setContribBusy] = useState(false);

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

  const loadGoals = useCallback(async () => {
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
            return [
              g.goal_id,
              {
                goal_id: g.goal_id,
                current_amount: g.start_amount ?? 0,
                target_amount: g.target_amount,
              } as GoalProgress,
            ] as const;
          }
        }),
      );

      setGoals(items);
      setProgressById(new Map(progEntries));
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load goals.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGoals();
  }, [loadGoals]);

  const toggleGoal = (g: Goal) => {
    if (expandedId === g.goal_id) {
      setExpandedId(null);
      setContribAmt("");
      return;
    }
    setExpandedId(g.goal_id);
    setContribAmt("");
    setEditName(g.name);
    setEditTarget(String(g.target_amount ?? ""));
    setEditTargetDate(g.target_date ? String(g.target_date).slice(0, 10) : "");
  };

  const addContribution = async (goalId: string) => {
    const amt = Number(String(contribAmt).replace(/,/g, ""));
    if (!Number.isFinite(amt) || amt <= 0) {
      setError("Enter a positive amount to add.");
      return;
    }
    setContribBusy(true);
    setError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}/contributions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            amount: amt,
            contribution_date: today,
            source: "manual",
          }),
        },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((data as any)?.detail, "Could not add contribution."));
      }
      setContribAmt("");
      await loadGoals();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Contribution failed.");
    } finally {
      setContribBusy(false);
    }
  };

  const saveGoal = async (goalId: string) => {
    setRowBusy(true);
    setError(null);
    try {
      const tgt = Number(String(editTarget).replace(/,/g, ""));
      if (!editName.trim()) throw new Error("Name is required.");
      if (!Number.isFinite(tgt) || tgt < 0) throw new Error("Enter a valid target amount.");
      const payload: Record<string, unknown> = {
        name: editName.trim(),
        target_amount: tgt,
      };
      if (editTargetDate.trim()) payload.target_date = editTargetDate.trim();
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((data as any)?.detail, "Could not save goal."));
      }
      setExpandedId(null);
      await loadGoals();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setRowBusy(false);
    }
  };

  const deleteGoal = (goalId: string) => {
    Alert.alert("Delete goal", "Remove this savings goal?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setRowBusy(true);
          setError(null);
          try {
            const res = await authClient.requestWithRefresh(
              `${GATEWAY_BASE_URL}/api/v1/goals/${encodeURIComponent(goalId)}`,
              { method: "DELETE" },
            );
            if (!res.ok) {
              const data = await res.json().catch(() => null);
              throw new Error(formatApiDetail((data as any)?.detail, "Delete failed."));
            }
            setExpandedId(null);
            await loadGoals();
          } catch (e: any) {
            setError(e?.message ? String(e.message) : "Delete failed.");
          } finally {
            setRowBusy(false);
          }
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      <ScrollView
        contentContainerStyle={[styles.container, { paddingTop: insets.top + 8 }]}
        keyboardShouldPersistTaps="handled"
      >
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
          <Text style={styles.hintMuted}>
            Tap a goal to add money or view progress. Use the chevron to edit or delete.
          </Text>

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

                const isOpen = expandedId === g.goal_id;
                return (
                  <ExpandableCard
                    key={g.goal_id}
                    expanded={isOpen}
                    onToggle={() => toggleGoal(g)}
                    onSummaryPress={() => router.push(`/goals/${encodeURIComponent(g.goal_id)}`)}
                    style={styles.goalCard}
                    summary={
                      <>
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
                      </>
                    }
                  >
                    <Pressable
                      onPress={() => router.push(`/goals/${encodeURIComponent(g.goal_id)}`)}
                      style={styles.openDetailLink}
                    >
                      <Text style={styles.openDetailLinkText}>Open full detail & contributions</Text>
                    </Pressable>
                    <Text style={styles.fieldLabel}>Add money</Text>
                    <Input
                      value={contribAmt}
                      onChangeText={setContribAmt}
                      placeholder="Amount"
                      keyboardType="decimal-pad"
                    />
                    <Button
                      title="Add to goal"
                      onPress={() => addContribution(g.goal_id)}
                      loading={contribBusy}
                      disabled={contribBusy}
                    />
                    <Text style={styles.fieldLabel}>Name</Text>
                    <Input value={editName} onChangeText={setEditName} placeholder="Goal name" />
                    <Text style={styles.fieldLabel}>Target amount</Text>
                    <Input
                      value={editTarget}
                      onChangeText={setEditTarget}
                      keyboardType="decimal-pad"
                      placeholder="0.00"
                    />
                    <Text style={styles.fieldLabel}>Target date (YYYY-MM-DD)</Text>
                    <Input value={editTargetDate} onChangeText={setEditTargetDate} placeholder="Optional" />
                    <View style={styles.rowActions}>
                      <View style={{ flex: 1 }}>
                        <Button
                          title="Save"
                          onPress={() => saveGoal(g.goal_id)}
                          loading={rowBusy}
                          disabled={rowBusy}
                        />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Button
                          title="Delete"
                          tone="danger"
                          onPress={() => deleteGoal(g.goal_id)}
                          disabled={rowBusy}
                        />
                      </View>
                    </View>
                  </ExpandableCard>
                );
              })
            ) : (
              <Text style={styles.mutedText}>No goals yet. Add one to get started.</Text>
            )}
          </View>
        </>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: theme.colors.background },
  fieldLabel: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  rowActions: { flexDirection: "row", gap: 10 },
  openDetailLink: { marginBottom: 4 },
  openDetailLinkText: {
    fontSize: 13,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.primary,
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
  hintMuted: {
    fontSize: 12,
    fontFamily: "Inter_500Medium",
    color: theme.colors.onSurfaceVariant,
    marginTop: 6,
    marginBottom: 4,
    lineHeight: 18,
  },
  progressOuter: { height: 10, borderRadius: 999, backgroundColor: theme.colors.outlineVariant, overflow: "hidden" },
  progressInner: { height: "100%", borderRadius: 999, backgroundColor: theme.colors.primary },
  goalCard: {
    marginBottom: 4,
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

