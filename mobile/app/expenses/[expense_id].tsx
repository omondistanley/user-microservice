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
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

type Tag = { name?: string; slug?: string };

type ExpenseDetail = {
  expense_id: string;
  date?: string;
  description?: string | null;
  name?: string | null;
  category_name?: string | null;
  category_code?: number | string | null;
  amount?: number | string | null;
  value?: number | string | null;
  source?: string | null;
  created_at?: string;
  plaid_transaction_id?: string | null;
  tags?: Tag[];
};

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${Math.abs(n).toFixed(2)}`;
}

function fmtWhen(date?: string, created?: string): { dateLine: string; timeLine: string } {
  const raw = date || created;
  if (!raw) return { dateLine: "—", timeLine: "" };
  try {
    const d = new Date(String(raw).includes("T") ? raw : `${raw}T12:00:00`);
    return {
      dateLine: d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
      timeLine: d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
    };
  } catch {
    return { dateLine: String(raw).slice(0, 10), timeLine: "" };
  }
}

function categoryIcon(name?: string | null): { icon: keyof typeof MaterialCommunityIcons.glyphMap; bg: string; ink: string } {
  const c = (name ?? "").toLowerCase();
  if (/(food|dining|coffee|restaurant)/.test(c)) {
    return { icon: "silverware-fork-knife", bg: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  if (/(transport|uber|car|gas)/.test(c)) {
    return { icon: "car", bg: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  if (/(shop|retail)/.test(c)) {
    return { icon: "shopping", bg: theme.colors.primaryContainer, ink: theme.colors.primary };
  }
  return { icon: "credit-card-outline", bg: theme.colors.primaryContainer, ink: theme.colors.primary };
}

export default function ExpenseDetailScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams();
  const expenseId = params.expense_id ? String(params.expense_id) : "";

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expense, setExpense] = useState<ExpenseDetail | null>(null);

  const load = useCallback(async () => {
    if (!expenseId) throw new Error("Missing expense id.");
    const res = await authClient.requestWithRefresh(
      `${GATEWAY_BASE_URL}/api/v1/expenses/${encodeURIComponent(expenseId)}`,
      { method: "GET" },
    );
    const data = (await res.json().catch(() => null)) as ExpenseDetail | null;
    if (!res.ok) throw new Error((data as any)?.detail ? String((data as any).detail) : "Failed to load expense.");
    return data;
  }, [expenseId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await load();
        if (cancelled) return;
        setExpense(data);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load expense.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const merchant = useMemo(
    () => String(expense?.description ?? expense?.name ?? expense?.category_name ?? "Transaction").trim() || "—",
    [expense],
  );
  const catName = expense?.category_name ?? "Uncategorized";
  const vis = categoryIcon(catName);
  const when = fmtWhen(expense?.date, expense?.created_at);
  const amt = expense?.amount ?? expense?.value;
  const synced = Boolean(expense?.plaid_transaction_id);
  const paymentLabel =
    expense?.source === "plaid"
      ? "Linked account"
      : expense?.source
        ? String(expense.source)
        : "Manual entry";

  const onDelete = () => {
    Alert.alert("Delete transaction", "This cannot be undone.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setBusy(true);
          try {
            const res = await authClient.requestWithRefresh(
              `${GATEWAY_BASE_URL}/api/v1/expenses/${encodeURIComponent(expenseId)}`,
              { method: "DELETE" },
            );
            if (!res.ok) {
              const j = await res.json().catch(() => null);
              throw new Error(j?.detail ? String(j.detail) : "Delete failed.");
            }
            router.back();
          } catch (e: any) {
            setError(e?.message ? String(e.message) : "Delete failed.");
          } finally {
            setBusy(false);
          }
        },
      },
    ]);
  };

  const onRepeat = () => {
    const n = toNumber(amt);
    router.push({
      pathname: "/expenses/add",
      params: {
        amount: n !== null ? String(Math.abs(n)) : "",
        note: merchant !== "—" ? merchant : "",
        kind: "expense",
      },
    });
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Expense Detail</Text>
        <Pressable hitSlop={12} onPress={onRepeat}>
          <MaterialCommunityIcons name="pencil-outline" size={22} color={theme.colors.primary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        showsVerticalScrollIndicator={false}
      >
        {loading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={theme.colors.primary} />
        ) : error ? (
          <Text style={styles.error}>{error}</Text>
        ) : expense ? (
          <>
            <View style={styles.hero}>
              <View style={[styles.heroIcon, { backgroundColor: vis.bg }]}>
                <MaterialCommunityIcons name={vis.icon} size={40} color={vis.ink} />
              </View>
              <Text style={styles.heroAmt}>-{fmtMoney(amt)}</Text>
              <Text style={styles.heroCat}>{catName}</Text>
            </View>

            <Text style={styles.sectionK}>Transaction details</Text>

            <Pressable style={styles.cardRow}>
              <View style={[styles.rowIcon, { backgroundColor: theme.colors.primaryContainer }]}>
                <MaterialCommunityIcons name="storefront-outline" size={22} color={theme.colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowK}>Merchant</Text>
                <Text style={styles.rowV}>{merchant}</Text>
              </View>
              <MaterialCommunityIcons name="chevron-right" size={22} color={theme.colors.secondary} />
            </Pressable>

            <View style={styles.divider} />

            <View style={styles.plainRow}>
              <MaterialCommunityIcons name="check-circle" size={22} color="#16a34a" />
              <Text style={styles.plainLabel}>Status</Text>
              <View style={styles.pillOk}>
                <Text style={styles.pillOkTxt}>{synced ? "Synced" : "Completed"}</Text>
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.plainRow}>
              <MaterialCommunityIcons name="calendar-outline" size={22} color={theme.colors.secondary} />
              <Text style={styles.plainLabel}>Date & time</Text>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={styles.rowV}>{when.dateLine}</Text>
                {when.timeLine ? <Text style={styles.timeSub}>{when.timeLine}</Text> : null}
              </View>
            </View>

            <View style={styles.divider} />

            <View style={styles.plainRow}>
              <MaterialCommunityIcons name="credit-card-outline" size={22} color={theme.colors.secondary} />
              <Text style={styles.plainLabel}>Payment method</Text>
              <Text style={styles.rowVRight}>{paymentLabel}</Text>
            </View>

            <View style={styles.notesHeader}>
              <MaterialCommunityIcons name="note-text-outline" size={18} color={theme.colors.secondary} />
              <Text style={styles.sectionK}>Notes & tags</Text>
            </View>
            <View style={styles.notesBox}>
              <Text style={styles.notesItalic}>
                {expense.description?.trim()
                  ? expense.description
                  : "No notes for this transaction."}
              </Text>
              {(expense.tags?.length ?? 0) > 0 ? (
                <View style={styles.tagRow}>
                  {expense.tags!.map((t, i) => (
                    <View key={`${t.slug ?? t.name ?? i}`} style={styles.tag}>
                      <Text style={styles.tagTxt}>{(t.name ?? t.slug ?? "").toUpperCase()}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>

            <View style={styles.mapPlaceholder}>
              <MaterialCommunityIcons name="map-marker" size={32} color={theme.colors.primary} />
              <Text style={styles.mapTxt}>Location unavailable for this entry</Text>
            </View>

            <Pressable style={styles.btnPrimary} onPress={onRepeat} disabled={busy}>
              <MaterialCommunityIcons name="refresh" size={22} color={theme.colors.onPrimary} />
              <Text style={styles.btnPrimaryTxt}>Repeat this expense</Text>
            </Pressable>

            <Pressable style={styles.btnDanger} onPress={onDelete} disabled={busy}>
              <MaterialCommunityIcons name="delete-outline" size={22} color={theme.colors.error} />
              <Text style={styles.btnDangerTxt}>Delete transaction</Text>
            </Pressable>
          </>
        ) : (
          <Text style={styles.muted}>No expense loaded.</Text>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  headerTitle: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  scroll: { paddingHorizontal: theme.spacing.xl, paddingTop: 16 },
  hero: { alignItems: "center", marginBottom: 28 },
  heroIcon: {
    width: 88,
    height: 88,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  heroAmt: { fontSize: 34, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  heroCat: { marginTop: 6, fontSize: 16, fontFamily: "Inter_500Medium", color: theme.colors.secondary },
  sectionK: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1.4,
    textTransform: "uppercase",
    marginBottom: 12,
  },
  cardRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 10,
  },
  rowIcon: {
    width: 44,
    height: 44,
    borderRadius: theme.radii.md,
    alignItems: "center",
    justifyContent: "center",
  },
  rowK: { fontSize: 11, fontFamily: "Inter_700Bold", color: theme.colors.secondary, letterSpacing: 0.8, textTransform: "uppercase" },
  rowV: { fontSize: 16, fontFamily: "Inter_700Bold", color: theme.colors.onSurface, marginTop: 2 },
  rowVRight: { flex: 1, textAlign: "right", fontSize: 14, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  divider: { height: 1, backgroundColor: theme.colors.outlineVariant, marginVertical: 4 },
  plainRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 12,
  },
  plainLabel: { flex: 1, fontSize: 15, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  timeSub: { fontSize: 13, color: theme.colors.secondary, fontFamily: "Inter_400Regular", marginTop: 2 },
  pillOk: {
    backgroundColor: "#dcfce7",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
  },
  pillOkTxt: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: "#166534" },
  notesHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 20, marginBottom: 10 },
  notesBox: {
    backgroundColor: theme.colors.surfaceContainerLow,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
  },
  notesItalic: { fontSize: 14, fontStyle: "italic", color: theme.colors.secondary, lineHeight: 20 },
  tagRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 12 },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: theme.colors.primaryContainer,
  },
  tagTxt: { fontSize: 11, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  mapPlaceholder: {
    marginTop: 20,
    height: 120,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  mapTxt: { fontSize: 12, color: theme.colors.secondary, fontFamily: "Inter_500Medium" },
  btnPrimary: {
    marginTop: 24,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    ...theme.shadows.sm,
  },
  btnPrimaryTxt: { color: theme.colors.onPrimary, fontSize: 16, fontFamily: "Inter_800ExtraBold" },
  btnDanger: {
    marginTop: 12,
    backgroundColor: "#fef2f2",
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    borderWidth: 1,
    borderColor: "#fecaca",
  },
  btnDangerTxt: { color: "#991b1b", fontSize: 16, fontFamily: "Inter_800ExtraBold" },
  error: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", marginTop: 12 },
  muted: { color: theme.colors.secondary },
});
