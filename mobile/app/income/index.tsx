import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type IncomeItem = {
  income_id?: string;
  amount?: number | string;
  date?: string;
  currency?: string;
  income_type?: string;
  source_label?: string | null;
  description?: string | null;
};

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

function fmtDate(iso?: string): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

export default function IncomeListScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [income, setIncome] = useState<IncomeItem[]>([]);
  const [search, setSearch] = useState("");
  const [incomeType, setIncomeType] = useState<string | null>(null);

  const query = useMemo(() => search.trim(), [search]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set("page", "1");
        params.set("page_size", "50");
        if (incomeType) params.set("income_type", incomeType);
        // API doesn't support free-text search; we'll filter client-side.

        const res = await authClient.requestWithRefresh(
          `${GATEWAY_BASE_URL}/api/v1/income?${params.toString()}`,
          { method: "GET" },
        );
        const data = await res.json().catch(() => null);
        const items = Array.isArray(data?.items) ? (data.items as IncomeItem[]) : [];

        const filtered =
          query.length > 0
            ? items.filter((it) => {
                const hay = `${it.description ?? ""} ${it.source_label ?? ""} ${it.income_type ?? ""}`.toLowerCase();
                return hay.includes(query.toLowerCase());
              })
            : items;

        if (cancelled) return;
        setIncome(filtered);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load income.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [query, incomeType]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Income</Text>
        <Pressable style={styles.addBtn} onPress={() => router.push("/income/add")}>
          <Text style={styles.addBtnText}>+ Add</Text>
        </Pressable>
      </View>

      <View style={styles.searchWrap}>
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Search (description/source/type)"
          autoCapitalize="none"
          style={styles.searchInput}
        />
      </View>

      <View style={styles.typeRow}>
        <Text style={styles.typeLabel}>Type:</Text>
        <Pressable style={styles.typeChip} onPress={() => setIncomeType(null)}>
          <Text style={styles.typeChipText}>All</Text>
        </Pressable>
        <Pressable style={styles.typeChip} onPress={() => setIncomeType("salary")}>
          <Text style={styles.typeChipText}>Salary</Text>
        </Pressable>
        <Pressable style={styles.typeChip} onPress={() => setIncomeType("other")}>
          <Text style={styles.typeChipText}>Other</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : income.length ? (
        income.map((it, idx) => (
          <View key={String(it.income_id ?? idx)} style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {it.description ?? it.source_label ?? it.income_type ?? "Income"}
              </Text>
              <Text style={styles.metaText}>{fmtDate(it.date)} • {it.income_type ?? "—"}</Text>
            </View>
            <Text style={styles.amountText}>{fmtMoney(it.amount)}</Text>
          </View>
        ))
      ) : (
        <Text style={styles.mutedText}>No income yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: "#fff" },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  title: { fontSize: 24, fontWeight: "900" },
  addBtn: { backgroundColor: "#135bec", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  addBtnText: { color: "#fff", fontWeight: "900" },
  searchWrap: { marginTop: -6 },
  searchInput: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  typeRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  typeLabel: { fontSize: 12, fontWeight: "900", color: "#64748b" },
  typeChip: { backgroundColor: "#f8fafc", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: "#e2e8f0" },
  typeChipText: { fontSize: 12, fontWeight: "900", color: "#0f172a" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    backgroundColor: "#fff",
  },
  rowTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a" },
  metaText: { fontSize: 12, color: "#64748b", marginTop: 4 },
  amountText: { fontSize: 14, fontWeight: "900", color: "#16a34a" },
  mutedText: { color: "#64748b" },
  errorText: { color: "#dc2626" },
});

