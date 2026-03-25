import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type RecurringItem = {
  recurring_id?: string;
  amount?: number | string;
  currency?: string;
  category_name?: string;
  category_code?: number | string;
  description?: string | null;
  recurrence_rule?: string;
  next_due_date?: string;
  is_active?: boolean;
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

export default function RecurringListScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<RecurringItem[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await authClient.requestWithRefresh(
          `${GATEWAY_BASE_URL}/api/v1/recurring-expenses?active_only=true&page=1&page_size=100`,
          { method: "GET" },
        );
        const data = await res.json().catch(() => null);
        const list = Array.isArray(data?.items) ? (data.items as RecurringItem[]) : [];
        if (cancelled) return;
        setItems(list);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load recurring.");
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
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Recurring</Text>
        <Pressable style={styles.addBtn} onPress={() => router.push("/recurring/add")}>
          <Text style={styles.addBtnText}>+ Add</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it, idx) => (
          <View key={String(it.recurring_id ?? idx)} style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle} numberOfLines={1}>
                {it.category_name ?? "Recurring"}
              </Text>
              <Text style={styles.metaText}>
                Next due: {fmtDate(it.next_due_date)} • {it.recurrence_rule ?? "—"}
              </Text>
              {it.description ? (
                <Text style={styles.descText} numberOfLines={1}>
                  {it.description}
                </Text>
              ) : null}
            </View>
            <Text style={styles.amountText}>{fmtMoney(it.amount)}</Text>
          </View>
        ))
      ) : (
        <Text style={styles.mutedText}>No recurring expenses yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: "#fff" },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { fontSize: 24, fontWeight: "900" },
  addBtn: { backgroundColor: "#135bec", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  addBtnText: { color: "#fff", fontWeight: "900" },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
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
  descText: { fontSize: 13, color: "#334155", marginTop: 6 },
  amountText: { fontSize: 14, fontWeight: "900", color: "#0f172a" },
  mutedText: { color: "#64748b" },
  errorText: { color: "#dc2626" },
});

