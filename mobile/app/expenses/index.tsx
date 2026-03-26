import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
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
import { theme } from "../../src/theme";
import { ExpandableCard } from "../../src/components/ui/ExpandableCard";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { agentLog } from "../../src/debug/agentLog";
import { formatApiDetail } from "../../src/formatApiDetail";

type ExpenseItem = {
  expense_id?: string;
  date?: string;
  description?: string;
  name?: string;
  category_name?: string;
  amount?: number | string;
  value?: number | string;
};

const CHIPS = ["ALL", "FOOD", "TRANSPORT", "SHOPPING"] as const;
type Chip = (typeof CHIPS)[number];

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtExpenseAmount(it: ExpenseItem): { text: string; isIncome: boolean } {
  const n = toNumber(it.amount ?? it.value ?? null);
  if (n === null) return { text: "—", isIncome: false };
  const abs = Math.abs(n);
  const cat = (it.category_name ?? "").toLowerCase();
  const incomeLike = /income|salary|deposit|payroll|payout/.test(cat);
  if (incomeLike) {
    return { text: `+$${abs.toFixed(2)}`, isIncome: true };
  }
  return { text: `-$${abs.toFixed(2)}`, isIncome: false };
}

function rowVisual(cat?: string): { icon: keyof typeof MaterialCommunityIcons.glyphMap; tile: string; ink: string } {
  const c = (cat ?? "").toLowerCase();
  if (/(food|dining|grocery|coffee|restaurant)/.test(c)) {
    return { icon: "silverware-fork-knife", tile: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  if (/(transport|uber|car|gas)/.test(c)) {
    return { icon: "car", tile: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  if (/(shop|retail)/.test(c)) {
    return { icon: "shopping", tile: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  if (/(income|salary|payout|deposit|payroll)/.test(c)) {
    return { icon: "cash", tile: theme.colors.tertiaryContainer, ink: theme.colors.onTertiaryContainer };
  }
  return { icon: "credit-card-outline", tile: theme.colors.surfaceContainer, ink: theme.colors.primary };
}

function groupLabel(iso: string): string {
  try {
    const d = new Date(iso + "T12:00:00");
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const ds = (x: Date) => x.toISOString().slice(0, 10);
    if (ds(d) === ds(today)) {
      return `TODAY, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" }).toUpperCase()}`;
    }
    if (ds(d) === ds(yesterday)) {
      return `YESTERDAY, ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" }).toUpperCase()}`;
    }
    return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" }).toUpperCase();
  } catch {
    return iso;
  }
}

function timePart(iso?: string): string {
  if (!iso) return "";
  if (iso.includes("T")) {
    try {
      return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    } catch {
      return "";
    }
  }
  return "";
}

export default function ExpensesScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<ExpenseItem[]>([]);
  const [search, setSearch] = useState("");
  const [chip, setChip] = useState<Chip>("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editDesc, setEditDesc] = useState("");
  const [editAmt, setEditAmt] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [rowBusy, setRowBusy] = useState(false);

  const loadExpenses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${GATEWAY_BASE_URL}/api/v1/expenses?page=1&page_size=80`;
      const res = await authClient.requestWithRefresh(url, { method: "GET" });
      const data = await res.json().catch(() => null);
      const list = data?.items && Array.isArray(data.items) ? data.items : [];
      setItems(list);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load expenses.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadExpenses();
  }, [loadExpenses]);

  const toggleExpense = (it: ExpenseItem) => {
    const id = it.expense_id ? String(it.expense_id) : "";
    if (!id) return;
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    setEditDesc(String(it.description ?? it.name ?? "").trim() || String(it.category_name ?? ""));
    const n = toNumber(it.amount ?? it.value);
    setEditAmt(n !== null ? String(Math.abs(n)) : "");
    setEditDate(it.date ? String(it.date).slice(0, 10) : "");
    setEditCategory(String(it.category_name ?? ""));
  };

  const saveExpense = async (expenseId: string) => {
    setRowBusy(true);
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
      if (editCategory.trim()) payload.category = editCategory.trim();
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/expenses/${encodeURIComponent(expenseId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );
      const data = await res.json().catch(() => null);
      agentLog({
        hypothesisId: "H1-H4",
        location: "expenses/index.tsx:saveExpense",
        message: "PATCH /expenses/{id} response",
        data: {
          httpStatus: res.status,
          ok: res.ok,
          payload,
          detailType: data && typeof (data as { detail?: unknown }).detail,
          detailJson: JSON.stringify((data as { detail?: unknown })?.detail ?? data).slice(0, 800),
        },
      });
      if (!res.ok) {
        throw new Error(formatApiDetail((data as any)?.detail, "Could not save expense."));
      }
      setExpandedId(null);
      await loadExpenses();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setRowBusy(false);
    }
  };

  const deleteExpense = (expenseId: string) => {
    Alert.alert("Delete expense", "This marks the expense as deleted.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setRowBusy(true);
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
            setExpandedId(null);
            await loadExpenses();
          } catch (e: any) {
            setError(e?.message ? String(e.message) : "Delete failed.");
          } finally {
            setRowBusy(false);
          }
        },
      },
    ]);
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((it) => {
      const cat = (it.category_name ?? "").toUpperCase();
      if (chip === "FOOD" && !/FOOD|DINING|GROCERY|RESTAURANT|COFFEE/.test(cat)) return false;
      if (chip === "TRANSPORT" && !/TRANSPORT|UBER|CAR|GAS|PARKING/.test(cat)) return false;
      if (chip === "SHOPPING" && !/SHOP|RETAIL|STORE/.test(cat)) return false;
      if (!q) return true;
      const blob = [it.description, it.name, it.category_name]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }, [items, search, chip]);

  const grouped = useMemo(() => {
    const m = new Map<string, ExpenseItem[]>();
    for (const it of filtered) {
      const d = it.date ? String(it.date).slice(0, 10) : "";
      const key = d || "unknown";
      const arr = m.get(key) ?? [];
      arr.push(it);
      m.set(key, arr);
    }
    return Array.from(m.entries()).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [filtered]);

  return (
    <View style={[styles.root, { backgroundColor: theme.colors.surfaceDim }]}>
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 24 },
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.inlineBackRow, pressed && { opacity: 0.85 }]}
          hitSlop={8}
        >
          <MaterialCommunityIcons name="arrow-left" size={22} color={theme.colors.primary} />
          <Text style={styles.inlineBackText}>Back</Text>
        </Pressable>
        <View style={styles.searchWrap}>
          <MaterialCommunityIcons name="magnify" size={20} color={theme.colors.secondary} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search transactions..."
            placeholderTextColor={theme.colors.secondary}
            style={styles.searchIn}
          />
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips}>
          {CHIPS.map((c) => {
            const on = chip === c;
            return (
              <Pressable key={c} style={[styles.chip, on && styles.chipOn]} onPress={() => setChip(c)}>
                <Text style={[styles.chipTxt, on && styles.chipTxtOn]}>{c}</Text>
              </Pressable>
            );
          })}
        </ScrollView>

        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={theme.colors.primary} />
        ) : error ? (
          <Text style={styles.error}>{error}</Text>
        ) : grouped.length ? (
          grouped.map(([date, list]) => (
            <View key={date} style={styles.group}>
              <Text style={styles.groupTitle}>{groupLabel(date)}</Text>
              {list.map((it, rowIdx) => {
                const id = it.expense_id ? String(it.expense_id) : null;
                const title = String(it.description ?? it.name ?? it.category_name ?? "Expense");
                const subCat = it.category_name ?? "";
                const t = timePart(it.date);
                const { text: amt, isIncome } = fmtExpenseAmount(it);
                const v = rowVisual(subCat);
                const open = Boolean(id && expandedId === id);
                return (
                  <ExpandableCard
                    key={String(it.expense_id ?? `${date}-${rowIdx}`)}
                    expanded={open}
                    onToggle={() => toggleExpense(it)}
                    style={styles.txCard}
                    summary={
                      <View style={styles.card}>
                        <View style={[styles.tile, { backgroundColor: v.tile }]}>
                          <MaterialCommunityIcons name={v.icon} size={22} color={v.ink} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.cardTitle} numberOfLines={1}>
                            {title}
                          </Text>
                          <Text style={styles.cardMeta} numberOfLines={1}>
                            {[t, subCat].filter(Boolean).join(" • ")}
                          </Text>
                        </View>
                        <Text style={[styles.cardAmt, isIncome ? styles.amtIn : styles.amtOut]}>{amt}</Text>
                      </View>
                    }
                  >
                    {id ? (
                      <>
                        <Pressable
                          onPress={() => router.push(`/expenses/${encodeURIComponent(id)}`)}
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
                        <Input value={editDate} onChangeText={setEditDate} />
                        <Text style={styles.fieldLabel}>Category</Text>
                        <Input value={editCategory} onChangeText={setEditCategory} />
                        <View style={styles.rowActions}>
                          <View style={{ flex: 1 }}>
                            <Button
                              title="Save"
                              onPress={() => saveExpense(id)}
                              loading={rowBusy}
                              disabled={rowBusy}
                            />
                          </View>
                          <View style={{ flex: 1 }}>
                            <Button
                              title="Delete"
                              tone="danger"
                              onPress={() => deleteExpense(id)}
                              disabled={rowBusy}
                            />
                          </View>
                        </View>
                      </>
                    ) : null}
                  </ExpandableCard>
                );
              })}
            </View>
          ))
        ) : (
          <Text style={styles.muted}>No expenses match.</Text>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  inlineBackRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    marginBottom: 12,
  },
  inlineBackText: {
    fontSize: 15,
    fontFamily: "Inter_700Bold",
    color: theme.colors.primary,
  },
  fieldLabel: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  rowActions: { flexDirection: "row", gap: 10 },
  txCard: { marginBottom: 10 },
  openDetailLink: { marginBottom: 4 },
  openDetailLinkText: {
    fontSize: 13,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.primary,
  },
  scroll: { padding: theme.spacing.lg },
  searchWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchIn: { flex: 1, fontSize: 15, fontFamily: "Inter_400Regular", color: theme.colors.onSurface },
  chips: { flexDirection: "row", gap: 10, paddingVertical: 14 },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  chipOn: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
  chipTxt: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary, letterSpacing: 0.5 },
  chipTxtOn: { color: theme.colors.onPrimary },
  group: { marginTop: 8, gap: 10 },
  groupTitle: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 0.8,
    marginTop: 8,
    marginBottom: 4,
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  tile: {
    width: 44,
    height: 44,
    borderRadius: theme.radii.md,
    alignItems: "center",
    justifyContent: "center",
  },
  cardTitle: { fontSize: 15, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  cardMeta: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.secondary, marginTop: 3 },
  cardAmt: { fontSize: 15, fontFamily: "Inter_800ExtraBold" },
  amtOut: { color: theme.colors.error },
  amtIn: { color: theme.colors.primary },
  error: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
  muted: { color: theme.colors.secondary, marginTop: 12 },
});
