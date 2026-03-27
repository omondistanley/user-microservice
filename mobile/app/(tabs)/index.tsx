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
import { formatApiDetail } from "../../src/formatApiDetail";

const R3 = 24;
const CHART_H = 200;

type CashflowSummary = {
  income_total?: number | string | null;
  expense_total?: number | string | null;
  savings?: number | string | null;
};

type BudgetItem = {
  budget_id?: string;
  name?: string | null;
  category_name?: string | null;
  category_code?: number | string | null;
  amount?: number | string | null;
};

type ExpenseSummaryItem = {
  group_key?: string | number | null;
  total_amount?: number | string | null;
};

type ExpenseItem = {
  expense_id?: string;
  date?: string;
  description?: string;
  name?: string;
  category_name?: string;
  category_code?: number | string | null;
  amount?: number | string;
  value?: number | string;
  created_at?: string;
  plaid_transaction_id?: string | null;
  teller_transaction_id?: string | null;
  source?: string | null;
};

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${n.toFixed(2)}`;
}

function readableExpenseLabel(it: ExpenseItem): string {
  const raw = String(it.description ?? it.name ?? "").trim();
  if (!raw || raw.toLowerCase().startsWith("fernet:") || raw.startsWith("gAAAAA")) {
    return String(it.category_name ?? "Expense");
  }
  return raw;
}

function categoryVisual(category?: string | null): { icon: keyof typeof MaterialCommunityIcons.glyphMap; tile: string; ink: string } {
  const c = (category ?? "").toLowerCase();
  if (/(food|dining|grocery|restaurant)/.test(c)) {
    return { icon: "silverware-fork-knife", tile: "#fff7ed", ink: "#ea580c" };
  }
  if (/(transport|uber|gas|fuel|car)/.test(c)) {
    return { icon: "car", tile: "#eff6ff", ink: "#2563eb" };
  }
  if (/(shop|retail|store|merch)/.test(c)) {
    return { icon: "cart-outline", tile: "#faf5ff", ink: "#9333ea" };
  }
  if (/(income|salary|payroll|deposit)/.test(c)) {
    return { icon: "bank", tile: "#ecfdf5", ink: "#059669" };
  }
  return { icon: "credit-card-outline", tile: theme.colors.surfaceContainer, ink: theme.colors.primary };
}

function formatExpenseSubtitle(isoDate?: string, createdAt?: string): string {
  const day = isoDate ? String(isoDate).slice(0, 10) : "";
  const now = new Date();
  const todayStr = toISODate(now);
  const y = new Date(now);
  y.setDate(y.getDate() - 1);
  const yStr = toISODate(y);
  const t = createdAt ? new Date(createdAt) : null;
  const timePart =
    t && !Number.isNaN(t.getTime())
      ? t.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
      : "";
  let dayPart = "";
  if (day === todayStr) dayPart = "Today";
  else if (day === yStr) dayPart = "Yesterday";
  else if (day) {
    const d = new Date(day + "T12:00:00");
    dayPart = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  return [dayPart, timePart].filter(Boolean).join(", ");
}

async function fetchAllExpensesInRange(dateFrom: string, dateTo: string): Promise<ExpenseItem[]> {
  const out: ExpenseItem[] = [];
  let page = 1;
  const pageSize = 100;
  while (page < 12) {
    const url = `${GATEWAY_BASE_URL}/api/v1/expenses?date_from=${dateFrom}&date_to=${dateTo}&page=${page}&page_size=${pageSize}`;
    const res = await authClient.requestWithRefresh(url, { method: "GET" });
    const data = (await res.json().catch(() => null)) as { items?: ExpenseItem[]; total?: number } | null;
    if (!res.ok) {
      throw new Error(formatApiDetail((data as any)?.detail, `Expenses failed (${res.status})`));
    }
    const items = Array.isArray(data?.items) ? data.items : [];
    out.push(...items);
    const total = Number(data?.total ?? 0);
    if (items.length < pageSize || out.length >= total) break;
    page += 1;
  }
  return out;
}

export default function DashboardScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [totalBalance, setTotalBalance] = useState<number | null>(null);
  const [momPct, setMomPct] = useState<number | null>(null);

  const [budgets, setBudgets] = useState<BudgetItem[]>([]);
  const [expenseSummaryByCategory, setExpenseSummaryByCategory] = useState<ExpenseSummaryItem[]>([]);

  const [chartDays, setChartDays] = useState<{ label: string; total: number; key: string }[]>([]);
  const [chartRangeLabel, setChartRangeLabel] = useState("");

  const [recent, setRecent] = useState<ExpenseItem[]>([]);

  const [expandedRecentId, setExpandedRecentId] = useState<string | null>(null);
  const [editDesc, setEditDesc] = useState("");
  const [editAmt, setEditAmt] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [recentBusy, setRecentBusy] = useState(false);

  const now = useMemo(() => new Date(), []);
  const firstDay = useMemo(() => toISODate(new Date(now.getFullYear(), now.getMonth(), 1)), [now]);
  const today = useMemo(() => toISODate(now), [now]);

  const lastMonthStart = useMemo(
    () => toISODate(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
    [now],
  );
  const lastMonthEnd = useMemo(() => toISODate(new Date(now.getFullYear(), now.getMonth(), 0)), [now]);

  const weekStart = useMemo(() => {
    const d = new Date(now);
    d.setDate(d.getDate() - 6);
    return toISODate(d);
  }, [now]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const cashThisUrl = `${GATEWAY_BASE_URL}/api/v1/cashflow/summary?date_from=${firstDay}&date_to=${today}&convert_to=USD`;
      const cashLastUrl = `${GATEWAY_BASE_URL}/api/v1/cashflow/summary?date_from=${lastMonthStart}&date_to=${lastMonthEnd}&convert_to=USD`;
      const nwUrl = `${GATEWAY_BASE_URL}/api/v1/net-worth/components`;
      const pfUrl = `${GATEWAY_BASE_URL}/api/v1/portfolio/value`;
      const budgetsUrl = `${GATEWAY_BASE_URL}/api/v1/budgets?page=1&page_size=10`;
      const expensesSummaryUrl = `${GATEWAY_BASE_URL}/api/v1/expenses/summary?group_by=category&date_from=${firstDay}&date_to=${today}&convert_to=USD`;
      const recentUrl = `${GATEWAY_BASE_URL}/api/v1/expenses?page=1&page_size=8`;

      const [cThisRes, cLastRes, nwRes, pfRes, bRes, sumRes, recRes] = await Promise.all([
        authClient.requestWithRefresh(cashThisUrl, { method: "GET" }),
        authClient.requestWithRefresh(cashLastUrl, { method: "GET" }),
        authClient.requestWithRefresh(nwUrl, { method: "GET" }),
        authClient.requestWithRefresh(pfUrl, { method: "GET" }),
        authClient.requestWithRefresh(budgetsUrl, { method: "GET" }),
        authClient.requestWithRefresh(expensesSummaryUrl, { method: "GET" }),
        authClient.requestWithRefresh(recentUrl, { method: "GET" }),
      ]);

      const cThis = (await cThisRes.json().catch(() => null)) as CashflowSummary | null;
      const cLast = (await cLastRes.json().catch(() => null)) as CashflowSummary | null;
      const nw = (await nwRes.json().catch(() => null)) as any;
      const pf = (await pfRes.json().catch(() => null)) as any;
      const bJson = (await bRes.json().catch(() => null)) as any;
      const sumJson = (await sumRes.json().catch(() => null)) as any;
      const recentJson = (await recRes.json().catch(() => null)) as any;
      const failures: [Response, any][] = [
        [cThisRes, cThis],
        [bRes, bJson],
        [sumRes, sumJson],
        [recRes, recentJson],
      ];
      for (const [res, payload] of failures) {
        if (!res.ok) {
          throw new Error(
            formatApiDetail(payload?.detail, `Dashboard request failed (${res.status})`),
          );
        }
      }

      let nwNet: number | null = null;
      if (nwRes.ok && nw) {
        const cash = toNumber(nw?.assets?.cash);
        const obligation = toNumber(nw?.liabilities?.spending_obligation);
        if (cash !== null && obligation !== null) {
          nwNet = cash - obligation;
        }
      }

      let mkt: number | null = null;
      if (pfRes.ok && pf) {
        mkt = toNumber(pf?.total_market_value);
      }

      if (nwNet !== null || mkt !== null) {
        setTotalBalance((nwNet ?? 0) + (mkt ?? 0));
      } else {
        setTotalBalance(null);
      }

      const incT = toNumber(cThis?.income_total);
      const expT = toNumber(cThis?.expense_total);
      const netT = incT !== null && expT !== null ? incT - expT : null;
      if (cLastRes.ok && cLast) {
        const incL = toNumber(cLast?.income_total);
        const expL = toNumber(cLast?.expense_total);
        const netL = incL !== null && expL !== null ? incL - expL : null;
        if (netT !== null && netL !== null && netL !== 0) {
          setMomPct(((netT - netL) / Math.abs(netL)) * 100);
        } else {
          setMomPct(null);
        }
      } else {
        setMomPct(null);
      }

      setBudgets(Array.isArray(bJson?.items) ? bJson.items : []);
      setExpenseSummaryByCategory(Array.isArray(sumJson?.items) ? sumJson.items : []);
      setRecent(Array.isArray(recentJson?.items) ? recentJson.items : []);

      let weekRows: ExpenseItem[] = [];
      try {
        weekRows = await fetchAllExpensesInRange(weekStart, today);
      } catch {
        weekRows = [];
      }
      const dayMap = new Map<string, number>();
      for (let i = 0; i < 7; i += 1) {
        const d = new Date(now);
        d.setDate(d.getDate() - (6 - i));
        dayMap.set(toISODate(d), 0);
        }
      for (const row of weekRows) {
        const dkey = row.date ? String(row.date).slice(0, 10) : "";
        if (!dkey || !dayMap.has(dkey)) continue;
        const amt = Math.abs(toNumber(row.amount ?? row.value) ?? 0);
        dayMap.set(dkey, (dayMap.get(dkey) ?? 0) + amt);
      }
      const orderedKeys = [...dayMap.keys()].sort();
      const days = orderedKeys.map((key) => {
        const dt = new Date(key + "T12:00:00");
        const label = dt.toLocaleDateString(undefined, { weekday: "short" }).toUpperCase();
        return { key, label, total: dayMap.get(key) ?? 0 };
      });
      setChartDays(days);
      if (orderedKeys.length >= 2) {
        const a = new Date(orderedKeys[0] + "T12:00:00");
        const b = new Date(orderedKeys[orderedKeys.length - 1] + "T12:00:00");
        setChartRangeLabel(
          `${a.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${b.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`,
        );
      } else {
        setChartRangeLabel("");
      }

    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, [firstDay, today, lastMonthEnd, lastMonthStart, now, weekStart]);

  useEffect(() => {
    load();
  }, [load]);

  const spentByCode = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of expenseSummaryByCategory) {
      const key = row.group_key !== null && row.group_key !== undefined ? String(row.group_key) : "";
      const amt = toNumber(row.total_amount);
      if (!key) continue;
      m.set(key, amt ?? 0);
    }
    return m;
  }, [expenseSummaryByCategory]);

  const topBudgets = budgets.slice(0, 3);
  const showGettingStarted = recent.length === 0 && budgets.length === 0;

  const maxDay = useMemo(() => Math.max(1, ...chartDays.map((d) => d.total)), [chartDays]);
  const hiIdx = useMemo(() => {
    const ixToday = chartDays.findIndex((d) => d.key === today);
    if (ixToday >= 0) return ixToday;
    let m = 0;
    let ix = 0;
    chartDays.forEach((d, i) => {
      if (d.total > m) {
        m = d.total;
        ix = i;
      }
    });
    return ix;
  }, [chartDays, today]);

  const toggleRecent = (it: ExpenseItem) => {
    const id = it.expense_id ? String(it.expense_id) : "";
    if (!id) return;
    if (expandedRecentId === id) {
      setExpandedRecentId(null);
      return;
    }
    setExpandedRecentId(id);
    const raw = String(it.description ?? it.name ?? "").trim();
    setEditDesc(raw || String(it.category_name ?? ""));
    const amtRaw = toNumber(it.amount ?? it.value);
    setEditAmt(amtRaw !== null ? String(Math.abs(amtRaw)) : "");
    setEditDate(it.date ? String(it.date).slice(0, 10) : "");
    setEditCategory(String(it.category_name ?? ""));
  };

  const saveRecentExpense = async (expenseId: string) => {
    setRecentBusy(true);
    setError(null);
    try {
      const amt = Number(String(editAmt).replace(/,/g, ""));
      if (!Number.isFinite(amt) || amt < 0) {
        throw new Error("Enter a valid amount.");
      }
      const payload: Record<string, unknown> = {
        description: editDesc.trim(),
        amount: amt,
        date: editDate.trim(),
      };
      if (editCategory.trim()) {
        payload.category = editCategory.trim();
      }
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/expenses/${encodeURIComponent(expenseId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((data as any)?.detail, "Could not save expense."));
      }
      setExpandedRecentId(null);
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setRecentBusy(false);
    }
  };

  const deleteRecentExpense = (expenseId: string) => {
    Alert.alert("Delete expense", "This marks the expense as deleted.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setRecentBusy(true);
          setError(null);
          try {
            const res = await authClient.requestWithRefresh(
              `${GATEWAY_BASE_URL}/api/v1/expenses/${encodeURIComponent(expenseId)}`,
              { method: "DELETE" },
            );
            if (!res.ok) {
              const data = await res.json().catch(() => null);
              throw new Error(formatApiDetail((data as any)?.detail, "Delete failed."));
            }
            setExpandedRecentId(null);
            await load();
          } catch (e: any) {
            setError(e?.message ? String(e.message) : "Delete failed.");
          } finally {
            setRecentBusy(false);
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={[
          styles.scrollBody,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 120 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {loading ? (
          <ActivityIndicator style={{ marginTop: 40 }} />
        ) : error ? (
          <Text style={styles.errorText}>{error}</Text>
        ) : (
          <>
            <View style={styles.hero} testID="e2e-dashboard-hero">
              <View style={styles.heroBlob} />
              <View style={{ zIndex: 1 }}>
                <Text style={styles.heroKicker}>TOTAL BALANCE</Text>
                <Text style={styles.heroAmount}>{totalBalance === null ? "—" : fmtMoney(totalBalance)}</Text>
                <View style={styles.heroBadge}>
                  <MaterialCommunityIcons name="trending-up" size={16} color="#4ade80" />
                  <Text style={styles.heroBadgeText}>
                    {momPct === null
                      ? "No month-over-month baseline yet"
                      : `${momPct >= 0 ? "+" : ""}${momPct.toFixed(1)}% this month`}
                  </Text>
                </View>
              </View>
            </View>

            {showGettingStarted ? (
              <View style={styles.getStartedCard}>
                <Text style={styles.getStartedKicker}>GET STARTED</Text>
                <Text style={styles.getStartedTitle}>Set up your first money workflow.</Text>
                <Text style={styles.getStartedSub}>
                  Add one transaction, create one budget, add one savings goal, or link a bank to unlock the rest of the dashboard.
                </Text>
                <View style={styles.getStartedGrid}>
                  <Pressable style={styles.getStartedBtnPrimary} onPress={() => router.push("/expenses/add")}>
                    <Text style={styles.getStartedBtnPrimaryText}>Add Expense</Text>
                  </Pressable>
                  <Pressable style={styles.getStartedBtnSecondary} onPress={() => router.push("/budgets/add")}>
                    <Text style={styles.getStartedBtnSecondaryText}>Create Budget</Text>
                  </Pressable>
                  <Pressable style={styles.getStartedBtnSecondary} onPress={() => router.push("/goals/add")}>
                    <Text style={styles.getStartedBtnSecondaryText}>Add Goal</Text>
                  </Pressable>
                  <Pressable style={styles.getStartedBtnSecondary} onPress={() => router.push("/link-bank")}>
                    <Text style={styles.getStartedBtnSecondaryText}>Link Bank</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            <View style={styles.surfaceCard}>
              <Text style={styles.sectionKickerMuted}>TOP CATEGORIES</Text>
              <View style={{ height: theme.spacing.lg }} />
              {topBudgets.length ? (
                topBudgets.map((b, idx) => {
                  const catCode =
                    b.category_code !== null && b.category_code !== undefined ? String(b.category_code) : "";
                  const spent = spentByCode.get(catCode) ?? 0;
                  const limit = toNumber(b.amount) ?? 0;
                  const pct = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 0;
                  const name = String(b.name ?? b.category_name ?? `Budget ${idx + 1}`);
                  const barColor =
                    pct >= 100 ? theme.colors.onSurface : idx === 1 ? `${theme.colors.primary}99` : theme.colors.primary;
                  return (
                    <View key={`${b.budget_id ?? idx}`} style={{ marginBottom: theme.spacing.xl }}>
                      <View style={styles.budgetHeaderRow}>
                        <Text style={styles.budgetName}>{name}</Text>
                        <Text style={styles.budgetFrac}>
                          {fmtMoney(spent)} / {limit ? fmtMoney(limit) : "—"}
                        </Text>
                      </View>
                      <View style={styles.track}>
                        <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: barColor }]} />
                      </View>
                    </View>
                  );
                })
              ) : (
                <Text style={styles.muted}>No budgets yet — add budgets to track category limits.</Text>
              )}
            </View>

            <View style={styles.surfaceCard}>
              <View style={styles.chartHeaderRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.chartTitle}>Weekly Spending</Text>
                  <Text style={styles.chartSub}>
                    {chartRangeLabel ? `Your activity from ${chartRangeLabel}` : "Your activity this week"}
                  </Text>
                </View>
                <View style={styles.weekActions}>
                  <Pressable style={styles.weekIconBtn} onPress={() => router.push("/(tabs)/transactions")}>
                    <MaterialCommunityIcons name="calendar-month-outline" size={22} color={theme.colors.secondary} />
                  </Pressable>
                  <Pressable style={styles.weekIconBtn} onPress={() => router.push("/more")}>
                    <MaterialCommunityIcons name="menu" size={22} color={theme.colors.secondary} />
                  </Pressable>
                </View>
              </View>
              <View style={[styles.chartArea, { height: CHART_H }]}>
                {chartDays.map((d, i) => {
                  const innerMax = CHART_H - 28;
                  const barPx = maxDay > 0 ? Math.max(6, (d.total / maxDay) * innerMax) : 6;
                  const active = i === hiIdx && d.total > 0;
                  return (
                    <View key={d.key} style={styles.chartCol}>
                      <View style={styles.chartBarTrack}>
                        <View
                          style={[
                            styles.chartBar,
                            { height: barPx },
                            active && styles.chartBarHi,
                          ]}
                        >
                          <View style={[styles.barSeg, { flex: 2, backgroundColor: theme.colors.primary }]} />
                          <View
                            style={[
                              styles.barSeg,
                              { flex: 1, backgroundColor: `${theme.colors.primary}66` },
                            ]}
                          />
                        </View>
                      </View>
                      <Text style={[styles.chartLbl, active && styles.chartLblHi]}>{d.label}</Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={styles.surfaceCard}>
              <View style={styles.txHead}>
                <Text style={styles.txTitle}>Recent transactions</Text>
                <Pressable onPress={() => router.push("/(tabs)/transactions")}>
                  <Text style={styles.viewAll}>VIEW ALL</Text>
                </Pressable>
              </View>
              {recent.length ? (
                recent.slice(0, 5).map((it, idx) => {
                  const cv = categoryVisual(it.category_name);
                  const when = formatExpenseSubtitle(it.date, it.created_at);
                  const sub = [it.category_name, when].filter(Boolean).join(" • ");
                  const amtRaw = toNumber(it.amount ?? it.value);
                  const isIncomeLike = /income|salary|pay|deposit|credit/i.test(it.category_name ?? "");
                  const amountLine =
                    amtRaw === null
                      ? "—"
                      : isIncomeLike
                        ? `+$${Math.abs(amtRaw).toFixed(2)}`
                        : `-$${Math.abs(amtRaw).toFixed(2)}`;
                  const eid = it.expense_id ? String(it.expense_id) : "";
                  const open = Boolean(eid && expandedRecentId === eid);
                  return (
                    <ExpandableCard
                      key={String(it.expense_id ?? idx)}
                      expanded={open}
                      onToggle={() => toggleRecent(it)}
                      style={styles.txExpandCard}
                      summary={
                        <View style={styles.txRow}>
                          <View style={styles.txLeft}>
                            <View style={[styles.txIconTile, { backgroundColor: cv.tile }]}>
                              <MaterialCommunityIcons name={cv.icon} size={22} color={cv.ink} />
                            </View>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.txName} numberOfLines={1}>
                                {readableExpenseLabel(it)}
                              </Text>
                              <Text style={styles.txSub} numberOfLines={2}>
                                {sub}
                              </Text>
                            </View>
                          </View>
                          <View style={styles.txRight}>
                            <Text
                              style={[
                                styles.txAmt,
                                isIncomeLike ? { color: "#059669" } : { color: theme.colors.error },
                              ]}
                            >
                              {amountLine}
                            </Text>
                          </View>
                        </View>
                      }
                    >
                      {eid ? (
                        <>
                          <Pressable
                            onPress={() =>
                              router.push(`/expenses/${encodeURIComponent(eid)}`)
                            }
                            style={styles.openDetailLink}
                          >
                            <Text style={styles.openDetailLinkText}>Open full detail</Text>
                          </Pressable>
                          <Text style={styles.fieldLabel}>Description</Text>
                          <Input value={editDesc} onChangeText={setEditDesc} placeholder="Description" />
                          <Text style={styles.fieldLabel}>Amount</Text>
                          <Input
                            value={editAmt}
                            onChangeText={setEditAmt}
                            keyboardType="decimal-pad"
                            placeholder="0.00"
                          />
                          <Text style={styles.fieldLabel}>Date (YYYY-MM-DD)</Text>
                          <Input value={editDate} onChangeText={setEditDate} placeholder="2025-01-15" />
                          <Text style={styles.fieldLabel}>Category</Text>
                          <Input value={editCategory} onChangeText={setEditCategory} placeholder="Category name" />
                          <View style={styles.rowActions}>
                            <View style={{ flex: 1 }}>
                              <Button
                                title="Save"
                                onPress={() => saveRecentExpense(eid)}
                                loading={recentBusy}
                                disabled={recentBusy}
                              />
                            </View>
                            <View style={{ flex: 1 }}>
                              <Button
                                title="Delete"
                                tone="danger"
                                onPress={() => deleteRecentExpense(eid)}
                                disabled={recentBusy}
                              />
                            </View>
                          </View>
                        </>
                      ) : null}
                    </ExpandableCard>
                  );
                })
              ) : (
                <Text style={styles.muted}>No transactions yet.</Text>
              )}
            </View>
          </>
        )}
      </ScrollView>

      <Pressable
        style={[styles.fab, { bottom: insets.bottom + 72 }]}
        onPress={() => router.push("/expenses/add")}
      >
        <MaterialCommunityIcons name="plus" size={30} color={theme.colors.onPrimary} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.background },
  fieldLabel: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  rowActions: { flexDirection: "row", gap: 10 },
  txExpandCard: { marginBottom: 10 },
  openDetailLink: { marginBottom: 4 },
  openDetailLinkText: {
    fontSize: 13,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.primary,
  },
  syncRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 },
  syncDot: { width: 8, height: 8, borderRadius: 4 },
  syncOn: { backgroundColor: "#34d399" },
  syncOff: { backgroundColor: theme.colors.outline },
  syncCaps: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.2,
  },
  scrollBody: { paddingHorizontal: theme.spacing.xl, paddingTop: theme.spacing.xl, gap: theme.spacing.xxl },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", marginTop: 12 },

  hero: {
    backgroundColor: "#0f172a",
    borderRadius: R3,
    padding: theme.spacing.xxl,
    overflow: "hidden",
  },
  heroBlob: {
    position: "absolute",
    right: -40,
    bottom: -40,
    width: 140,
    height: 140,
    borderRadius: 70,
    backgroundColor: `${theme.colors.primary}33`,
  },
  heroKicker: {
    color: "rgba(255,255,255,0.6)",
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    letterSpacing: 2,
  },
  heroAmount: {
    color: "#fff",
    fontSize: 36,
    fontFamily: "Inter_800ExtraBold",
    marginTop: 8,
    letterSpacing: -0.5,
  },
  heroBadge: {
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    alignSelf: "flex-start",
    backgroundColor: "rgba(255,255,255,0.1)",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: theme.radii.full,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.12)",
  },
  heroBadgeText: { color: "#4ade80", fontSize: 13, fontFamily: "Inter_600SemiBold" },
  getStartedCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: R3,
    padding: theme.spacing.xxl,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    gap: 10,
  },
  getStartedKicker: {
    color: theme.colors.primary,
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    letterSpacing: 2,
  },
  getStartedTitle: {
    color: theme.colors.onSurface,
    fontSize: 22,
    fontFamily: "Inter_800ExtraBold",
  },
  getStartedSub: {
    color: theme.colors.onSurfaceVariant,
    fontSize: 13,
    lineHeight: 18,
    fontFamily: "Inter_400Regular",
  },
  getStartedGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 4,
  },
  getStartedBtnPrimary: {
    minWidth: "47%",
    flexGrow: 1,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  getStartedBtnPrimaryText: {
    color: theme.colors.onPrimary,
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  getStartedBtnSecondary: {
    minWidth: "47%",
    flexGrow: 1,
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    alignItems: "center",
    justifyContent: "center",
  },
  getStartedBtnSecondaryText: {
    color: theme.colors.onSurface,
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    textTransform: "uppercase",
    letterSpacing: 1,
  },

  investCard: {
    backgroundColor: "rgba(238,242,255,0.65)",
    borderRadius: R3,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    padding: theme.spacing.xxl,
  },
  investHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: theme.spacing.lg },
  rowStart: { flexDirection: "row", alignItems: "center", gap: 8 },
  sectionKickerPrimary: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.primary,
    letterSpacing: 2,
  },
  investValue: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  investInner: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}18`,
    alignItems: "center",
    gap: theme.spacing.md,
  },
  strategyTitle: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  strategyBody: {
    fontSize: 11,
    lineHeight: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    textAlign: "center",
  },
  primaryBtn: {
    width: "100%",
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  primaryBtnText: { color: theme.colors.onPrimary, fontSize: 12, fontFamily: "Inter_700Bold" },

  insightsShell: {
    backgroundColor: `${theme.colors.primary}0D`,
    borderRadius: R3,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    padding: theme.spacing.xxl,
    gap: theme.spacing.md,
  },
  insightCard: {
    backgroundColor: theme.colors.surface + "99",
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.surface,
    padding: theme.spacing.lg,
  },
  insightGreen: { backgroundColor: "#ecfdf5", borderColor: "#a7f3d0" },
  insightTitle: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurface, marginBottom: 6 },
  insightBody: { fontSize: 11, lineHeight: 16, color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular" },

  surfaceCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: R3,
    padding: theme.spacing.xxl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
  },
  sectionKickerMuted: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 2,
  },
  budgetHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" },
  budgetName: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  budgetFrac: { fontSize: 12, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurfaceVariant },
  track: {
    marginTop: 8,
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainer,
    overflow: "hidden",
  },
  barFill: { height: "100%", borderRadius: 999 },
  muted: { color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular", fontSize: 13 },

  chartHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: theme.spacing.xl },
  weekActions: { flexDirection: "row", alignItems: "center", gap: 4 },
  weekIconBtn: {
    padding: 8,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainerLow,
  },
  chartTitle: { fontSize: 22, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  chartSub: { fontSize: 13, color: theme.colors.onSurfaceVariant, marginTop: 4, fontFamily: "Inter_400Regular" },
  legend: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: theme.colors.primary },
  legendText: { fontSize: 10, fontFamily: "Inter_700Bold", color: theme.colors.onSurfaceVariant },

  chartArea: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 8, paddingHorizontal: 4 },
  chartCol: { flex: 1, alignItems: "center", gap: 8, justifyContent: "flex-end" },
  chartBarTrack: { width: "100%", alignItems: "center", justifyContent: "flex-end", minHeight: CHART_H - 24 },
  chartBar: {
    width: "88%",
    flexDirection: "column-reverse",
    borderTopLeftRadius: 10,
    borderTopRightRadius: 10,
    overflow: "hidden",
  },
  chartBarHi: {
    transform: [{ scaleX: 1.04 }],
    shadowColor: theme.colors.primary,
    shadowOpacity: 0.35,
    shadowRadius: 8,
    elevation: 4,
  },
  barSeg: { width: "100%" },
  chartLbl: { fontSize: 10, fontFamily: "Inter_700Bold", color: theme.colors.onSurfaceVariant },
  chartLblHi: { color: theme.colors.primary },

  txHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: theme.spacing.lg },
  txTitle: { fontSize: 20, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  viewAll: { fontSize: 10, fontFamily: "Inter_700Bold", color: theme.colors.primary, letterSpacing: 2 },

  txRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: theme.spacing.md,
    paddingHorizontal: theme.spacing.sm,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: "transparent",
    marginBottom: 4,
  },
  txLeft: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md, flex: 1, paddingRight: 8 },
  txIconTile: { width: 48, height: 48, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  txName: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  txSub: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginTop: 4, fontFamily: "Inter_400Regular" },
  txRight: { alignItems: "flex-end" },
  txAmt: { fontSize: 14, fontFamily: "Inter_800ExtraBold" },
  syncStatusRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  syncCapsSm: { fontSize: 10, fontFamily: "Inter_700Bold" },

  fab: {
    position: "absolute",
    right: theme.spacing.xl,
    width: 58,
    height: 58,
    borderRadius: 18,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    ...theme.shadows.md,
  },
});
