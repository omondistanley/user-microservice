import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { getAccessToken } from "../../src/authTokens";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";

type Anomaly = {
  expense_id?: string;
  date?: string;
  amount?: number | string;
  category_name?: string;
  category_code?: number | string;
  reason?: string;
  detail?: string;
};

type ForecastSpendResponse = {
  message?: string;
  months_back?: number;
  data_points?: number;
  method?: string;
  projections?: Array<{
    month?: string;
    projected_amount?: number | string;
    confidence_low?: number | string;
    confidence_high?: number | string;
  }>;
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

export default function InsightsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [hub, setHub] = useState<"monthly" | "quarterly" | "yearly">("monthly");
  const [initial, setInitial] = useState("•");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [forecast, setForecast] = useState<ForecastSpendResponse | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const anomaliesRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/insights/anomalies?limit=25`, {
        method: "GET",
      });
      const anomaliesJson = await anomaliesRes.json().catch(() => null);
      if (!anomaliesRes.ok) {
        throw new Error(formatApiDetail(anomaliesJson?.detail, "Failed to load anomalies."));
      }
      const pts = Array.isArray(anomaliesJson?.anomalies) ? (anomaliesJson.anomalies as Anomaly[]) : [];

      const forecastRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/insights/forecast/spend?months_back=6`, {
        method: "GET",
      });
      const forecastJson = (await forecastRes.json().catch(() => null)) as ForecastSpendResponse | null;
      if (!forecastRes.ok) {
        throw new Error(formatApiDetail((forecastJson as any)?.detail, "Failed to load forecast."));
      }

      setAnomalies(pts);
      setForecast(forecastJson);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load insights.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const anomaliesTop = useMemo(() => anomalies.slice(0, 12), [anomalies]);

  const submitFeedback = async (expenseId: string, feedback: "valid" | "ignore") => {
    try {
      const url = `${GATEWAY_BASE_URL}/api/v1/insights/anomalies/${encodeURIComponent(expenseId)}/feedback?feedback=${feedback}`;
      const res = await authClient.requestWithRefresh(url, { method: "POST" });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Feedback failed."));
      }
      // Refresh list to reflect any changes (or at least to keep UI in sync).
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Feedback failed.");
    }
  };

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + 8 }]}>
      <View style={styles.hubBar}>
        <View style={styles.hubLeft}>
          <View style={styles.hubAv}>
            <Text style={styles.hubAvTxt}>{initial}</Text>
          </View>
          <Text style={styles.hubBrand}>pocketii</Text>
        </View>
        <Pressable onPress={() => router.push("/notifications")}>
          <MaterialCommunityIcons name="bell-outline" size={24} color={theme.colors.primary} />
        </Pressable>
      </View>
      <Text style={styles.hubK}>Analysis hub</Text>
      <Text style={styles.hubTitle}>Financial insights</Text>
      <View style={styles.hubSeg}>
        {(["monthly", "quarterly", "yearly"] as const).map((h) => (
          <Pressable key={h} style={[styles.hubSegBtn, hub === h && styles.hubSegOn]} onPress={() => setHub(h)}>
            <Text style={[styles.hubSegTxt, hub === h && styles.hubSegTxtOn]}>
              {h === "monthly" ? "Monthly" : h === "quarterly" ? "Quarterly" : "Yearly"}
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Details</Text>
        <View style={{ width: 60 }} />
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Forecast spend (next 3 months)</Text>
            {forecast?.message ? <Text style={styles.mutedText}>{forecast.message}</Text> : null}
            <Text style={styles.mutedText}>
              Method: {forecast?.method ?? "—"} • Data points: {forecast?.data_points ?? "—"}
            </Text>
            <View style={styles.projList}>
              {(forecast?.projections ?? []).map((p, idx) => (
                <View key={`${p.month ?? idx}`} style={styles.projRow}>
                  <Text style={styles.projMonth}>{p.month ?? "—"}</Text>
                  <Text style={styles.projAmount}>{fmtMoney(p.projected_amount)}</Text>
                  <Text style={styles.projCI}>
                    CI: {fmtMoney(p.confidence_low)} - {fmtMoney(p.confidence_high)}
                  </Text>
                </View>
              ))}
              {(forecast?.projections ?? []).length === 0 ? <Text style={styles.mutedText}>No forecast yet.</Text> : null}
            </View>
          </View>

          <View style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.sectionTitle}>Anomaly candidates</Text>
              <Pressable onPress={load} style={styles.smallBtn}>
                <Text style={styles.smallBtnText}>Refresh</Text>
              </Pressable>
            </View>

            {anomaliesTop.length ? (
              anomaliesTop.map((a, idx) => (
                <View key={`${a.expense_id ?? idx}`} style={styles.anomRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.anomTitle} numberOfLines={1}>
                      {a.category_name ?? (a.category_code ? `Category ${a.category_code}` : "Expense")}
                    </Text>
                    <Text style={styles.anomMeta}>
                      {fmtDate(a.date)} • {fmtMoney(a.amount)} • {a.reason ?? "—"}
                    </Text>
                    {a.detail ? (
                      <Text style={styles.anomDetail} numberOfLines={2}>
                        {a.detail}
                      </Text>
                    ) : null}
                  </View>

                  <View style={styles.feedbackBtns}>
                    <Pressable
                      onPress={() => (a.expense_id ? submitFeedback(a.expense_id, "valid") : null)}
                      style={styles.feedbackBtnGood}
                    >
                      <Text style={styles.feedbackBtnText}>Valid</Text>
                    </Pressable>
                    <Pressable
                      onPress={() => (a.expense_id ? submitFeedback(a.expense_id, "ignore") : null)}
                      style={styles.feedbackBtnBad}
                    >
                      <Text style={styles.feedbackBtnText}>Ignore</Text>
                    </Pressable>
                  </View>
                </View>
              ))
            ) : (
              <Text style={styles.mutedText}>No anomalies found.</Text>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: "#f8f9fb" },
  hubBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  hubLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  hubAv: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "#dbeafe",
    alignItems: "center",
    justifyContent: "center",
  },
  hubAvTxt: { fontSize: 15, fontWeight: "900", color: theme.colors.primary },
  hubBrand: { fontSize: 17, fontWeight: "900", color: "#0f172a" },
  hubK: {
    fontSize: 11,
    fontWeight: "800",
    color: theme.colors.primary,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    marginTop: 8,
  },
  hubTitle: { fontSize: 26, fontWeight: "900", color: "#0f172a", marginBottom: 12 },
  hubSeg: {
    flexDirection: "row",
    backgroundColor: "#e2e8f0",
    borderRadius: 12,
    padding: 4,
    gap: 4,
    marginBottom: 16,
  },
  hubSegBtn: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: "center" },
  hubSegOn: { backgroundColor: "#fff", shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 4, shadowOffset: { width: 0, height: 1 } },
  hubSegTxt: { fontSize: 13, fontWeight: "800", color: "#64748b" },
  hubSegTxtOn: { color: theme.colors.primary },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backBtn: { width: 60 },
  backText: { color: "#135bec", fontWeight: "900" },
  title: { fontSize: 24, fontWeight: "900" },
  card: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, gap: 10, backgroundColor: "#fff" },
  sectionTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a" },
  mutedText: { color: "#64748b", fontWeight: "900", fontSize: 12 },
  errorText: { color: "#dc2626", fontWeight: "900" },
  projList: { gap: 10 },
  projRow: { borderWidth: 1, borderColor: "#f1f5f9", borderRadius: 14, padding: 12, backgroundColor: "#fff" },
  projMonth: { fontSize: 13, fontWeight: "900", color: "#0f172a" },
  projAmount: { fontSize: 16, fontWeight: "900", color: "#0f172a", marginTop: 4 },
  projCI: { fontSize: 12, fontWeight: "900", color: "#64748b", marginTop: 4 },
  cardHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  smallBtn: { backgroundColor: "#f8fafc", borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 },
  smallBtnText: { fontWeight: "900", color: "#0f172a" },
  anomRow: { flexDirection: "row", gap: 10, borderWidth: 1, borderColor: "#f1f5f9", borderRadius: 14, padding: 12, backgroundColor: "#fff" },
  anomTitle: { fontSize: 13, fontWeight: "900", color: "#0f172a" },
  anomMeta: { fontSize: 12, fontWeight: "900", color: "#64748b", marginTop: 4 },
  anomDetail: { fontSize: 12, fontWeight: "900", color: "#334155", marginTop: 6 },
  feedbackBtns: { width: 132, gap: 8, justifyContent: "flex-start" },
  feedbackBtnGood: { backgroundColor: "#dcfce7", borderWidth: 1, borderColor: "#86efac", borderRadius: 12, paddingVertical: 10, alignItems: "center" },
  feedbackBtnBad: { backgroundColor: "#fee2e2", borderWidth: 1, borderColor: "#fca5a5", borderRadius: 12, paddingVertical: 10, alignItems: "center" },
  feedbackBtnText: { fontWeight: "900", color: "#0f172a" },
});

