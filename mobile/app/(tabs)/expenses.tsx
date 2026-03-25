import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

export default function ExpensesScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await authClient.requestWithRefresh(
          `${GATEWAY_BASE_URL}/api/v1/expenses?page=1&page_size=20`,
          { method: "GET" },
        );
        const data = await res.json().catch(() => null);
        const list = (data && data.items && Array.isArray(data.items) ? data.items : data) || [];
        if (cancelled) return;
        setItems(Array.isArray(list) ? list : []);
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

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Expenses</Text>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it: any) => {
          const date = it?.date ? String(it.date).slice(0, 10) : "";
          const name =
            String(it?.description || it?.name || it?.category_name || it?.category || "Expense");
          const amount = it?.amount != null ? String(it.amount) : it?.value != null ? String(it.value) : "—";
          return (
            <View key={String(it?.expense_id ?? `${date}-${name}`)} style={styles.row}>
              <View style={styles.left}>
                <Text style={styles.dateText}>{date || "—"}</Text>
                <Text style={styles.nameText} numberOfLines={1}>
                  {name}
                </Text>
              </View>
              <Text style={styles.amountText}>{amount}</Text>
            </View>
          );
        })
      ) : (
        <Text style={styles.cardText}>No expenses yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 10 },
  title: { fontSize: 22, fontWeight: "700" },
  errorText: { color: "#dc2626" },
  cardText: { color: "#334155", marginTop: 6 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e2e8f0",
  },
  left: { flex: 1, paddingRight: 10 },
  dateText: { fontSize: 12, color: "#64748b" },
  nameText: { fontSize: 14, fontWeight: "600", color: "#0f172a" },
  amountText: { fontSize: 14, fontWeight: "700", color: "#0f172a" },
});

