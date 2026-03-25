import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

export default function TransactionsScreen() {
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
          `${GATEWAY_BASE_URL}/api/v1/transactions?page=1&page_size=25`,
          { method: "GET" },
        );
        const data = await res.json().catch(() => null);
        const list = (data && data.items && Array.isArray(data.items) ? data.items : data) || [];
        if (cancelled) return;
        setItems(Array.isArray(list) ? list : []);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load transactions.");
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
      <Text style={styles.title}>Transactions</Text>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it: any) => {
          const entryType = String(it?.entry_type || "transaction");
          const occurred = it?.occurred_on ? String(it.occurred_on).slice(0, 10) : "—";
          const desc = String(it?.description || it?.category_name || "—");
          const amount = it?.amount != null ? Number(it.amount) : 0;
          const sign = entryType === "income" ? 1 : -1;
          const display = `${sign === 1 ? "+" : "-"}$${Math.abs(amount).toFixed(2)}`;
          return (
            <View key={String(it?.transaction_id ?? it?.entry_id ?? `${occurred}-${desc}`)} style={styles.row}>
              <View style={{ flex: 1, paddingRight: 10 }}>
                <Text style={styles.dateText}>{occurred}</Text>
                <Text style={styles.descText} numberOfLines={1}>
                  {desc}
                </Text>
                <Text style={styles.typeText}>{entryType}</Text>
              </View>
              <Text style={[styles.amountText, sign === 1 ? styles.income : styles.expense]}>{display}</Text>
            </View>
          );
        })
      ) : (
        <Text style={styles.cardText}>No transactions yet.</Text>
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
  dateText: { fontSize: 12, color: "#64748b" },
  descText: { fontSize: 14, fontWeight: "700", color: "#0f172a", marginTop: 4 },
  typeText: { fontSize: 12, color: "#64748b", marginTop: 2, textTransform: "capitalize" },
  amountText: { fontSize: 14, fontWeight: "900", textAlign: "right" },
  income: { color: "#16a34a" },
  expense: { color: "#0f172a" },
});

