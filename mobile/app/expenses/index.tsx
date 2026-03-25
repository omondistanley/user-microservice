import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
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
import { getAccessToken } from "../../src/authTokens";
import { theme } from "../../src/theme";

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
  const [initial, setInitial] = useState("•");

  useEffect(() => {
    let c = true;
    (async () => {
      const t = await getAccessToken();
      if (!c || !t) return;
      try {
        const res = await fetch(`${GATEWAY_BASE_URL}/user/me`, { headers: { Authorization: `Bearer ${t}` } });
        const data = await res.json().catch(() => null);
        if (data?.first_name) setInitial(String(data.first_name).charAt(0).toUpperCase());
        else if (data?.email) setInitial(String(data.email).charAt(0).toUpperCase());
      } catch {
        /* ignore */
      }
    })();
    return () => {
      c = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const url = `${GATEWAY_BASE_URL}/api/v1/expenses?page=1&page_size=80`;
        const res = await authClient.requestWithRefresh(url, { method: "GET" });
        const data = await res.json().catch(() => null);
        const list = data?.items && Array.isArray(data.items) ? data.items : [];
        if (cancelled) return;
        setItems(list);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load expenses.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
    <View style={[styles.root, { backgroundColor: theme.colors.surfaceDim, paddingTop: insets.top }]}>
      <View style={styles.top}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.topTitle}>
            Transactions <Text style={styles.brand}>Indigo Vault</Text>
          </Text>
        </View>
        <View style={styles.av}>
          <Text style={styles.avTxt}>{initial}</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
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
                return (
                  <Pressable
                    key={String(it.expense_id ?? `${date}-${rowIdx}`)}
                    style={styles.card}
                    onPress={id ? () => router.push(`/expenses/${encodeURIComponent(id)}`) : undefined}
                  >
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
                  </Pressable>
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
  top: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: 10,
    backgroundColor: theme.colors.surface,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  topTitle: { fontSize: 15, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  brand: { fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  av: {
    width: 36,
    height: 36,
    borderRadius: 999,
    backgroundColor: theme.colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  avTxt: { fontFamily: "Inter_800ExtraBold", color: theme.colors.primary, fontSize: 14 },
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
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: 14,
    ...theme.shadows.sm,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
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
