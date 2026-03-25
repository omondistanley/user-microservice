import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

export default function DashboardScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<any | null>(null);
  const [surplus, setSurplus] = useState<any | null>(null);
  const [recommendations, setRecommendations] = useState<any | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const urls = [
          `${GATEWAY_BASE_URL}/api/v1/sync-status`,
          `${GATEWAY_BASE_URL}/api/v1/surplus`,
          `${GATEWAY_BASE_URL}/api/v1/recommendations/latest?page=1&page_size=5&enrich=0`,
        ];
        const [s1, s2, s3] = await Promise.all(
          urls.map((u) => authClient.requestWithRefresh(u, { method: "GET" })),
        );

        const json1 = await s1.json().catch(() => null);
        const json2 = await s2.json().catch(() => null);
        const json3 = await s3.json().catch(() => null);

        if (cancelled) return;
        setSyncStatus(json1);
        setSurplus(json2);
        setRecommendations(json3);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load dashboard.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const recItems = recommendations?.items;

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.title}>Dashboard</Text>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Connection</Text>
          <Text style={styles.cardText}>
            Bank linked: {syncStatus?.bank_linked ? "Yes" : "No"}
          </Text>
          <Text style={styles.cardText}>
            Last sync update:{" "}
            {syncStatus?.last_bank_connection_update_at
              ? String(syncStatus.last_bank_connection_update_at)
              : "—"}
          </Text>
        </View>
      )}

      {!loading && !error ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Surplus</Text>
          <Text style={styles.cardText}>
            Investable surplus:{" "}
            {surplus && typeof surplus === "object" ? String(surplus.investable_surplus ?? "—") : "—"}
          </Text>
        </View>
      ) : null}

      {!loading && !error ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Latest recommendations</Text>
          {Array.isArray(recItems) && recItems.length ? (
            recItems.map((it: any, idx: number) => (
              <View key={String(it?.recommendation_id ?? idx)} style={styles.recRow}>
                <Text style={styles.recTitle}>{it?.title ?? it?.symbol ?? "Recommendation"}</Text>
                {it?.summary ? (
                  <Text style={styles.recSubtitle} numberOfLines={2}>
                    {String(it.summary)}
                  </Text>
                ) : null}
              </View>
            ))
          ) : (
            <Text style={styles.cardText}>No recommendations yet.</Text>
          )}
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 14 },
  title: { fontSize: 22, fontWeight: "700" },
  errorText: { color: "#dc2626", marginTop: 8 },
  card: {
    backgroundColor: "#f8fafc",
    borderRadius: 14,
    padding: 14,
    gap: 8,
  },
  cardTitle: { fontSize: 16, fontWeight: "700" },
  cardText: { fontSize: 14, color: "#334155" },
  recRow: { gap: 4, marginTop: 8, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: "#e2e8f0" },
  recTitle: { fontSize: 15, fontWeight: "600" },
  recSubtitle: { fontSize: 13, color: "#475569" },
});
