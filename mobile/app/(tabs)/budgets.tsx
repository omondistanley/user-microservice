import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

export default function BudgetsScreen() {
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
          `${GATEWAY_BASE_URL}/api/v1/budgets?page=1&page_size=100`,
          { method: "GET" },
        );
        const data = await res.json().catch(() => null);
        const list = (data && data.items && Array.isArray(data.items) ? data.items : data) || [];
        if (cancelled) return;
        setItems(Array.isArray(list) ? list : []);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load budgets.");
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
      <Text style={styles.title}>Budgets</Text>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it: any) => {
          const name = String(it?.name || it?.category_name || it?.category_code || "Budget");
          const amount = it?.amount != null ? String(it.amount) : "—";
          const start = it?.start_date ? String(it.start_date).slice(0, 10) : "—";
          const end = it?.end_date ? String(it.end_date).slice(0, 10) : "—";
          return (
            <View key={String(it?.budget_id ?? name)} style={styles.row}>
              <View style={{ flex: 1, paddingRight: 10 }}>
                <Text style={styles.nameText} numberOfLines={1}>
                  {name}
                </Text>
                <Text style={styles.metaText}>Start: {start}</Text>
                <Text style={styles.metaText}>End: {end}</Text>
              </View>
              <Text style={styles.amountText}>{amount}</Text>
            </View>
          );
        })
      ) : (
        <Text style={styles.cardText}>No budgets yet.</Text>
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
  nameText: { fontSize: 14, fontWeight: "700", color: "#0f172a" },
  metaText: { fontSize: 12, color: "#64748b", marginTop: 4 },
  amountText: { fontSize: 14, fontWeight: "800", color: "#0f172a", textAlign: "right" },
});

