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
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { ExpandableCard } from "../../src/components/ui/ExpandableCard";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { agentLog } from "../../src/debug/agentLog";
import { formatApiDetail } from "../../src/formatApiDetail";

type BudgetItem = {
  budget_id?: string;
  name?: string | null;
  category_name?: string | null;
  category_code?: number | string | null;
  amount?: number | string | null;
  start_date?: string | null;
  end_date?: string | null;
};

type ExpenseSummaryItem = {
  group_key?: string | number | null;
  total_amount?: number | string | null;
};

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtMoney(n: number): string {
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function categoryVisual(category?: string | null): {
  icon: keyof typeof MaterialCommunityIcons.glyphMap;
  tile: string;
  ink: string;
} {
  const c = (category ?? "").toLowerCase();
  if (/(food|dining|grocery|restaurant)/.test(c)) {
    return { icon: "silverware-fork-knife", tile: "#fff7ed", ink: "#ea580c" };
  }
  if (/(movie|film|stream|entertain|game|music)/.test(c)) {
    return { icon: "movie-open-outline", tile: "#eef2ff", ink: theme.colors.primary };
  }
  if (/(transport|uber|gas|fuel|car)/.test(c)) {
    return { icon: "car", tile: "#f1f5f9", ink: "#475569" };
  }
  if (/(shop|retail|store|merch)/.test(c)) {
    return { icon: "shopping-outline", tile: "#f0fdfa", ink: "#0d9488" };
  }
  if (/(income|salary|payroll|deposit)/.test(c)) {
    return { icon: "bank", tile: "#ecfdf5", ink: "#059669" };
  }
  return { icon: "wallet-outline", tile: theme.colors.surfaceContainer, ink: theme.colors.primary };
}

function daysLeftInMonth(from: Date): number {
  const y = from.getFullYear();
  const m = from.getMonth();
  const last = new Date(y, m + 1, 0).getDate();
  return Math.max(0, last - from.getDate());
}

export default function BudgetsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [budgets, setBudgets] = useState<BudgetItem[]>([]);
  const [spentByCode, setSpentByCode] = useState<Map<string, number>>(new Map());
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editAmount, setEditAmount] = useState("");
  const [editStart, setEditStart] = useState("");
  const [editEnd, setEditEnd] = useState("");
  const [rowBusy, setRowBusy] = useState(false);

  const now = useMemo(() => new Date(), []);
  const firstDay = useMemo(() => toISODate(new Date(now.getFullYear(), now.getMonth(), 1)), [now]);
  const today = useMemo(() => toISODate(now), [now]);
  const monthLabel = useMemo(
    () =>
      now.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
    [now],
  );

  const loadBudgets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const budgetsUrl = `${GATEWAY_BASE_URL}/api/v1/budgets?page=1&page_size=100`;
      const expensesSummaryUrl = `${GATEWAY_BASE_URL}/api/v1/expenses/summary?group_by=category&date_from=${firstDay}&date_to=${today}&convert_to=USD`;

      const [budRes, expRes] = await Promise.all([
        authClient.requestWithRefresh(budgetsUrl, { method: "GET" }),
        authClient.requestWithRefresh(expensesSummaryUrl, { method: "GET" }),
      ]);

      const budgetsPayload = await budRes.json().catch(() => null);
      const expPayload = await expRes.json().catch(() => null);

      if (!budRes.ok) {
        throw new Error(formatApiDetail((budgetsPayload as any)?.detail, "Failed to load budgets."));
      }
      if (!expRes.ok) {
        throw new Error(
          formatApiDetail((expPayload as any)?.detail, "Failed to load spend summary."),
        );
      }

      const list =
        budgetsPayload?.items && Array.isArray(budgetsPayload.items)
          ? budgetsPayload.items
          : [];
      const expItems =
        expPayload?.items && Array.isArray(expPayload.items) ? expPayload.items : [];

      const map = new Map<string, number>();
      for (const r of expItems as ExpenseSummaryItem[]) {
        const key = r.group_key !== null && r.group_key !== undefined ? String(r.group_key) : "";
        if (!key) continue;
        map.set(key, toNumber(r.total_amount) ?? 0);
      }

      setBudgets(list);
      setSpentByCode(map);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load budgets.");
    } finally {
      setLoading(false);
    }
  }, [firstDay, today]);

  useEffect(() => {
    loadBudgets();
  }, [loadBudgets]);

  const toggleBudget = (b: BudgetItem) => {
    const id = b.budget_id ? String(b.budget_id) : "";
    if (!id) return;
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    setEditName(String(b.name ?? b.category_name ?? ""));
    setEditAmount(
      b.amount !== null && b.amount !== undefined ? String(b.amount) : "",
    );
    setEditStart(b.start_date ? String(b.start_date).slice(0, 10) : "");
    setEditEnd(b.end_date ? String(b.end_date).slice(0, 10) : "");
  };

  const saveBudget = async (budgetId: string) => {
    setRowBusy(true);
    setError(null);
    try {
      const amt = Number(String(editAmount).replace(/,/g, ""));
      if (!Number.isFinite(amt) || amt < 0) {
        throw new Error("Enter a valid amount.");
      }
      const payload: Record<string, unknown> = {
        name: editName.trim() || undefined,
        amount: amt,
      };
      if (editStart.trim()) payload.start_date = editStart.trim();
      if (editEnd.trim()) payload.end_date = editEnd.trim();

      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/budgets/${encodeURIComponent(budgetId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await res.json().catch(() => null);
      agentLog({
        hypothesisId: "H1-H3",
        location: "budgets.tsx:saveBudget",
        message: "PATCH /budgets/{id} response",
        data: {
          httpStatus: res.status,
          ok: res.ok,
          payloadKeys: Object.keys(payload),
          detailType: data && typeof (data as { detail?: unknown }).detail,
          detailJson: JSON.stringify((data as { detail?: unknown })?.detail ?? data).slice(0, 800),
        },
      });
      if (!res.ok) {
        throw new Error(formatApiDetail((data as any)?.detail, "Could not save budget."));
      }
      await loadBudgets();
      setExpandedId(null);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setRowBusy(false);
    }
  };

  const deleteBudget = (budgetId: string) => {
    Alert.alert("Delete budget", "This removes the budget permanently.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setRowBusy(true);
          setError(null);
          try {
            const res = await authClient.requestWithRefresh(
              `${GATEWAY_BASE_URL}/api/v1/budgets/${encodeURIComponent(budgetId)}`,
              { method: "DELETE" },
            );
            if (!res.ok) {
              const data = await res.json().catch(() => null);
              throw new Error(formatApiDetail((data as any)?.detail, "Delete failed."));
            }
            setExpandedId(null);
            await loadBudgets();
          } catch (e: any) {
            setError(e?.message ? String(e.message) : "Delete failed.");
          } finally {
            setRowBusy(false);
          }
        },
      },
    ]);
  };

  const { totalBudgeted, totalSpent, pctOverall, remaining } = useMemo(() => {
    let tb = 0;
    let ts = 0;
    for (const b of budgets) {
      const limit = toNumber(b.amount) ?? 0;
      const catCode =
        b.category_code !== null && b.category_code !== undefined
          ? String(b.category_code)
          : "";
      const spent = catCode ? spentByCode.get(catCode) ?? 0 : 0;
      tb += limit;
      ts += spent;
    }
    const pct = tb > 0 ? Math.min(100, Math.round((ts / tb) * 100)) : 0;
    const rem = Math.max(0, tb - ts);
    return { totalBudgeted: tb, totalSpent: ts, pctOverall: pct, remaining: rem };
  }, [budgets, spentByCode]);

  const daysLeft = useMemo(() => daysLeftInMonth(now), [now]);

  return (
    <View style={[styles.root, { backgroundColor: theme.colors.surfaceDim }]}>
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 8 },
          { paddingBottom: insets.bottom + 100 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.heroTitles}>
          <Text style={styles.pageTitle}>Budgets</Text>
          <Text style={styles.pageSub}>
            Maintain your financial discipline with precision.
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={theme.colors.primary} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : (
          <>
            <View style={styles.summaryColumn}>
              <View style={styles.cardBudgeted}>
                <Text style={styles.capsLightOnPrimary}>Total Budgeted</Text>
                <Text style={styles.hugeWhite}>{fmtMoney(totalBudgeted)}</Text>
                <View style={styles.monthRow}>
                  <MaterialCommunityIcons name="calendar-month-outline" size={16} color="rgba(255,255,255,0.9)" />
                  <Text style={styles.monthText}>{monthLabel}</Text>
                </View>
              </View>

              <View style={styles.cardWhite}>
                <Text style={styles.capsMuted}>Total Spent</Text>
                <Text style={styles.hugeDark}>{fmtMoney(totalSpent)}</Text>
                <View style={styles.barTrack}>
                  <View style={[styles.barFill, { width: `${pctOverall}%` }]} />
                </View>
                <Text style={styles.footerMuted}>
                  {pctOverall}% of total budget used
                </Text>
              </View>

              <View style={styles.cardWhite}>
                <Text style={styles.capsMuted}>Remaining</Text>
                <Text style={styles.hugePrimary}>{fmtMoney(remaining)}</Text>
                <View style={styles.remainRow}>
                  <Text style={styles.italicMuted}>{daysLeft} days left</Text>
                  <Pressable onPress={() => router.push("/settings")}>
                    <Text style={styles.linkBold}>Adjust Limits</Text>
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.catHeader}>
              <Text style={styles.sectionTitle}>Categories</Text>
              <Pressable
                style={styles.addCatBtn}
                onPress={() => router.push("/budgets/add")}
              >
                <MaterialCommunityIcons name="plus" size={16} color={theme.colors.onSurface} />
                <Text style={styles.addCatText}>Add Budget</Text>
              </Pressable>
            </View>

            {budgets.length === 0 ? (
              <View style={styles.emptyCard}>
                <Text style={styles.empty}>No budgets yet.</Text>
                <Text style={styles.emptySub}>
                  Create your first category limit so the mobile dashboard and alerts have something to track.
                </Text>
                <Button title="Create Budget" onPress={() => router.push("/budgets/add")} />
              </View>
            ) : (
              budgets.map((b, idx) => {
                const catCode =
                  b.category_code !== null && b.category_code !== undefined
                    ? String(b.category_code)
                    : "";
                const spent = catCode ? spentByCode.get(catCode) ?? 0 : 0;
                const limit = toNumber(b.amount) ?? 0;
                const title = String(b.name ?? b.category_name ?? `Budget ${idx + 1}`);
                const sub = (() => {
                  const cn = b.category_name?.trim();
                  if (cn && cn !== title) return cn;
                  return "Budget category";
                })();
                const pct = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 0;
                const over = limit > 0 && spent > limit;
                const warn = !over && pct >= 80;
                const barColor = over ? theme.colors.error : warn ? theme.colors.tertiary : theme.colors.primary;
                const vis = categoryVisual(`${title} ${sub}`);

                const statusLabel = over
                  ? "Over budget"
                  : warn
                    ? `${pct}% used`
                    : `${pct}% used`;
                const statusColor = over
                  ? theme.colors.error
                  : warn
                    ? theme.colors.tertiary
                    : theme.colors.primary;

                const left = limit - spent;
                const leftLabel = over
                  ? `Exceeded by ${fmtMoney(Math.abs(left))}`
                  : `${fmtMoney(Math.max(0, left))} left`;

                const footerStatus = over
                  ? "Status: over limit"
                  : warn
                    ? "Warning threshold: 80%"
                    : pct >= 50
                      ? "Status: on track"
                      : "Status: healthy";

                const bid = b.budget_id ? String(b.budget_id) : "";
                const isOpen = bid && expandedId === bid;

                return (
                  <ExpandableCard
                    key={String(b.budget_id ?? idx)}
                    expanded={Boolean(isOpen)}
                    onToggle={() => toggleBudget(b)}
                    style={styles.catCard}
                    summary={
                      <>
                        <View style={styles.catTop}>
                          <View style={styles.catLeft}>
                            <View style={[styles.iconTile, { backgroundColor: vis.tile }]}>
                              <MaterialCommunityIcons name={vis.icon} size={22} color={vis.ink} />
                            </View>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.catTitle} numberOfLines={1}>
                                {title}
                              </Text>
                              <Text style={styles.catSub} numberOfLines={1}>
                                {sub}
                              </Text>
                            </View>
                          </View>
                          <View style={{ alignItems: "flex-end" }}>
                            <Text style={styles.catAmounts}>
                              {fmtMoney(spent)} / {fmtMoney(limit)}
                            </Text>
                            <Text style={[styles.catPct, { color: statusColor }]}>
                              {statusLabel.toUpperCase()}
                            </Text>
                          </View>
                        </View>
                        <View style={styles.barTrackThick}>
                          <View
                            style={[
                              styles.barFillThick,
                              {
                                width: `${Math.min(100, limit > 0 ? (spent / limit) * 100 : 0)}%`,
                                backgroundColor: barColor,
                              },
                            ]}
                          />
                        </View>
                        <View style={styles.catFooter}>
                          <Text style={styles.catFooterLeft}>{footerStatus}</Text>
                          <Text
                            style={[
                              styles.catFooterRight,
                              over && { color: theme.colors.error },
                            ]}
                          >
                            {leftLabel}
                          </Text>
                        </View>
                      </>
                    }
                  >
                    {bid ? (
                      <>
                        <Text style={styles.fieldLabel}>Name</Text>
                        <Input value={editName} onChangeText={setEditName} placeholder="Budget name" />
                        <Text style={styles.fieldLabel}>Amount limit</Text>
                        <Input
                          value={editAmount}
                          onChangeText={setEditAmount}
                          placeholder="0.00"
                          keyboardType="decimal-pad"
                        />
                        <Text style={styles.fieldLabel}>Start date (YYYY-MM-DD)</Text>
                        <Input value={editStart} onChangeText={setEditStart} placeholder="2025-01-01" />
                        <Text style={styles.fieldLabel}>End date (YYYY-MM-DD)</Text>
                        <Input value={editEnd} onChangeText={setEditEnd} placeholder="2025-12-31" />
                        <View style={styles.rowActions}>
                          <View style={{ flex: 1 }}>
                            <Button
                              title="Save"
                              onPress={() => saveBudget(bid)}
                              loading={rowBusy}
                              disabled={rowBusy}
                            />
                          </View>
                          <View style={{ flex: 1 }}>
                            <Button
                              title="Delete"
                              tone="danger"
                              onPress={() => deleteBudget(bid)}
                              disabled={rowBusy}
                            />
                          </View>
                        </View>
                      </>
                    ) : null}
                  </ExpandableCard>
                );
              })
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: { paddingHorizontal: theme.spacing.xl, paddingTop: 16 },
  fieldLabel: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  rowActions: { flexDirection: "row", gap: 10 },
  heroTitles: { marginBottom: 24 },
  pageTitle: {
    fontSize: 28,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginBottom: 6,
  },
  pageSub: {
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
  },
  summaryColumn: { gap: 16, marginBottom: 28 },
  cardBudgeted: {
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.xxl,
    ...theme.shadows.md,
  },
  capsLightOnPrimary: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: "rgba(255,255,255,0.85)",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  hugeWhite: {
    fontSize: 30,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
    marginTop: 8,
  },
  monthRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 24 },
  monthText: { fontSize: 12, fontFamily: "Inter_600SemiBold", color: "rgba(255,255,255,0.95)" },
  cardWhite: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.xxl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  capsMuted: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  hugeDark: {
    fontSize: 30,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginTop: 8,
  },
  hugePrimary: {
    fontSize: 30,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
    marginTop: 8,
  },
  barTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainerHigh,
    overflow: "hidden",
    marginTop: 24,
  },
  barFill: {
    height: "100%",
    borderRadius: 999,
    backgroundColor: theme.colors.primary,
  },
  footerMuted: {
    marginTop: 8,
    fontSize: 12,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.onSurfaceVariant,
  },
  remainRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 24,
  },
  italicMuted: {
    fontSize: 12,
    fontFamily: "Inter_600SemiBold",
    fontStyle: "italic",
    color: theme.colors.onSurfaceVariant,
  },
  linkBold: {
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    color: theme.colors.primary,
  },
  catHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 20,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
  },
  addCatBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainer,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  addCatText: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    letterSpacing: 1.2,
    textTransform: "uppercase",
    color: theme.colors.onSurface,
  },
  catCard: {
    marginBottom: 16,
  },
  catTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 16,
  },
  catLeft: { flexDirection: "row", alignItems: "flex-start", gap: 12, flex: 1 },
  iconTile: {
    width: 48,
    height: 48,
    borderRadius: theme.radii.md,
    alignItems: "center",
    justifyContent: "center",
  },
  catTitle: { fontSize: 16, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  catSub: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.onSurfaceVariant, marginTop: 2 },
  catAmounts: { fontSize: 13, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  catPct: { fontSize: 10, fontFamily: "Inter_800ExtraBold", marginTop: 4, letterSpacing: 1 },
  barTrackThick: {
    height: 10,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainerHigh,
    overflow: "hidden",
  },
  barFillThick: { height: "100%", borderRadius: 999 },
  catFooter: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
  },
  catFooterLeft: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  catFooterRight: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  emptyCard: {
    gap: 10,
    padding: 16,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  empty: { color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular", marginTop: 8 },
  emptySub: {
    color: theme.colors.onSurfaceVariant,
    fontFamily: "Inter_400Regular",
    lineHeight: 18,
  },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", marginTop: 8 },
});
