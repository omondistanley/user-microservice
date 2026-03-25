import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, Button } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type RecommendationItem = {
  symbol?: string;
  score?: string;
  confidence?: string;
  full_name?: string;
  sector?: string;
  why_shown_one_line?: string;
  bull_case?: string;
  bear_case?: string;
  data_badges?: any[];
};

type LatestResponse = {
  run?: any;
  items?: RecommendationItem[];
  page_state?: string;
  pagination?: { page: number; page_size: number; total_items: number; total_pages: number };
};

export default function RecommendationsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<LatestResponse | null>(null);

  const fetchLatest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/recommendations/latest?page=1&page_size=50`, {
        method: "GET",
      });
      const json = (await res.json().catch(() => null)) as LatestResponse | null;
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to load recommendations.");
      setResp(json);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await fetchLatest();
      if (cancelled) return;
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const items: RecommendationItem[] = useMemo(() => resp?.items ?? [], [resp]);

  const runNow = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/recommendations/run`, {
        method: "POST",
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Run failed.");
      await fetchLatest();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Run failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Recommendations</Text>
        <View style={{ width: 60 }} />
      </View>

      <View style={styles.actionsRow}>
        <View style={{ flex: 1 }}>
          {running ? <ActivityIndicator /> : <Button title="Run now" onPress={runNow} />}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it, idx) => (
          <View key={`${String(it.symbol ?? "sym")}-${idx}`} style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowTitle}>{it.symbol ?? "—"}</Text>
              {it.full_name ? <Text style={styles.fullName}>{it.full_name}</Text> : null}
              <Text style={styles.subText}>{it.why_shown_one_line ?? ""}</Text>
              {it.sector ? <Text style={styles.metaText}>Sector: {it.sector}</Text> : null}
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={styles.scoreText}>Score: {it.score ?? "—"}</Text>
              <Text style={styles.confText}>Conf: {it.confidence ?? "—"}</Text>
            </View>
          </View>
        ))
      ) : (
        <Text style={styles.mutedText}>No recommendations yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, backgroundColor: "#fff", gap: 12 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backBtn: { width: 60 },
  backText: { color: "#135bec", fontWeight: "900" },
  title: { fontSize: 24, fontWeight: "900" },
  actionsRow: { flexDirection: "row", gap: 10, alignItems: "center" },
  errorText: { color: "#dc2626" },
  row: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 16,
    padding: 14,
    backgroundColor: "#fff",
    flexDirection: "row",
    gap: 12,
    alignItems: "flex-start",
  },
  rowTitle: { fontSize: 16, fontWeight: "900", color: "#0f172a" },
  fullName: { fontSize: 13, color: "#334155", marginTop: 3 },
  subText: { fontSize: 12, color: "#475569", marginTop: 6, flexWrap: "wrap" },
  metaText: { fontSize: 12, color: "#64748b", marginTop: 6 },
  scoreText: { fontSize: 12, fontWeight: "900", color: "#0f172a" },
  confText: { fontSize: 12, fontWeight: "900", color: "#64748b", marginTop: 4 },
  mutedText: { color: "#64748b" },
});

