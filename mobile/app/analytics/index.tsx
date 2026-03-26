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

type AnalyticsOverviewResponse = {
  period?: { date_from?: string; date_to?: string; days?: number };
  income_total?: string;
  expense_total?: string;
  net?: string;
  spend_by_category?: Array<{
    category_code?: number | string;
    label?: string;
    total?: string;
    count?: number;
  }>;
};

type NetWorthSummary = {
  net_worth?: number | string;
  assets_total?: number | string;
  liabilities_total?: number | string;
  assets?: Record<string, number | string>;
  liabilities?: Record<string, number | string>;
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

function fmtMoneyBig(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const CASHFLOW_DAYS = [30, 90, 365] as const;
const NW_RANGE = ["1M", "6M", "1Y", "ALL"] as const;

export default function AnalyticsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [initial, setInitial] = useState("•");
  const [loading, setLoading] = useState(true);
  const [nwLoading, setNwLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nwError, setNwError] = useState<string | null>(null);
  const [days, setDays] = useState<number>(30);
  const [nwVisual, setNwVisual] = useState<(typeof NW_RANGE)[number]>("1M");
  const [data, setData] = useState<AnalyticsOverviewResponse | null>(null);
  const [nwData, setNwData] = useState<NetWorthSummary | null>(null);

  const fetchOverview = async (d: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/analytics/overview?days=${d}`, {
        method: "GET",
      });
      const json = (await res.json().catch(() => null)) as AnalyticsOverviewResponse | null;
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Failed to load analytics."));
      }
      setData(json);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load analytics.");
    } finally {
      setLoading(false);
    }
  };

  const fetchNw = async () => {
    setNwLoading(true);
    setNwError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/summary`, {
        method: "GET",
      });
      const json = (await res.json().catch(() => null)) as NetWorthSummary | null;
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Failed to load net worth."));
      }
      setNwData(json);
    } catch (e: any) {
      setNwError(e?.message ? String(e.message) : "Failed to load net worth.");
    } finally {
      setNwLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview(days);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  useEffect(() => {
    fetchNw();
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

  const topCategories = useMemo(() => {
    const list = data?.spend_by_category ?? [];
    return list.slice(0, 6);
  }, [data]);

  const assetsTotal = toNumber(nwData?.assets_total);
  const liabilitiesTotal = toNumber(nwData?.liabilities_total);
  const nw = toNumber(nwData?.net_worth);

  const assetLines = useMemo(() => {
    const a = nwData?.assets ?? {};
    const rows: { label: string; val: number }[] = [
      { label: "Cash & liquidity", val: toNumber(a.cash) ?? 0 },
      { label: "Equities", val: toNumber(a.investments) ?? 0 },
      { label: "Budgets", val: toNumber(a.budgets) ?? 0 },
      { label: "Manual assets", val: toNumber(a.manual) ?? 0 },
    ].filter((r) => r.val > 0);
    rows.sort((x, y) => y.val - x.val);
    return rows.slice(0, 3);
  }, [nwData?.assets]);

  const liabilityLines = useMemo(() => {
    const L = nwData?.liabilities ?? {};
    const rows: { label: string; val: number; dot: string }[] = [
      { label: "Spending obligation", val: toNumber(L.expenses) ?? 0, dot: theme.colors.error },
      { label: "Manual liabilities", val: toNumber(L.manual) ?? 0, dot: theme.colors.tertiary },
      { label: "Debt", val: toNumber(L.debt) ?? 0, dot: "#7c3aed" },
    ].filter((r) => r.val > 0);
    return rows.slice(0, 3);
  }, [nwData?.liabilities]);

  const debtToAssetPct = useMemo(() => {
    if (assetsTotal === null || liabilitiesTotal === null || assetsTotal <= 0) return null;
    return (liabilitiesTotal / assetsTotal) * 100;
  }, [assetsTotal, liabilitiesTotal]);

  const netFlow = toNumber(data?.net);
  const avgMonthlyFlow = useMemo(() => {
    if (netFlow === null || days <= 0) return null;
    return (netFlow / days) * 30;
  }, [netFlow, days]);

  const liquidityLabel = useMemo(() => {
    if (assetsTotal === null || liabilitiesTotal === null || liabilitiesTotal <= 0) return "—";
    const ratio = assetsTotal / liabilitiesTotal;
    if (ratio >= 3) return "A+";
    if (ratio >= 2) return "A";
    if (ratio >= 1.2) return "B+";
    return "B";
  }, [assetsTotal, liabilitiesTotal]);

  return (
    <ScrollView contentContainerStyle={[styles.container, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.appBar}>
        <View style={styles.appBarLeft}>
          <View style={styles.av}>
            <Text style={styles.avTxt}>{initial}</Text>
          </View>
          <Text style={styles.brand}>pocketii</Text>
        </View>
        <Pressable hitSlop={12} onPress={() => router.push("/notifications")}>
          <MaterialCommunityIcons name="bell-outline" size={24} color={theme.colors.primary} />
        </Pressable>
      </View>
      <Text style={styles.execK}>Executive overview</Text>
      <Text style={styles.bigTitle}>Portfolio analytics</Text>
      <View style={styles.actionRow}>
        <Pressable style={styles.outlineBtn} onPress={() => router.push("/reports")}>
          <MaterialCommunityIcons name="download-outline" size={18} color={theme.colors.onSurface} />
          <Text style={styles.outlineBtnTxt}>Export report</Text>
        </Pressable>
        <Pressable style={styles.fillBtn} onPress={() => router.push("/net-worth/breakdown")}>
          <MaterialCommunityIcons name="plus" size={18} color={theme.colors.onPrimary} />
          <Text style={styles.fillBtnTxt}>New asset</Text>
        </Pressable>
      </View>

      {nwLoading ? (
        <ActivityIndicator style={{ marginVertical: 8 }} />
      ) : nwError ? (
        <Text style={styles.errorText}>{nwError}</Text>
      ) : (
        <>
          <View style={styles.nwCard}>
            <View style={styles.nwTopRow}>
              <Text style={styles.nwK}>Current net worth</Text>
              <Text style={styles.nwHuge}>{fmtMoneyBig(nw)}</Text>
              <View style={styles.trendRow}>
                <MaterialCommunityIcons name="trending-up" size={18} color="#059669" />
                <Text style={styles.trendTxt}>Live summary from your accounts</Text>
              </View>
              <View style={styles.nwSeg}>
                {NW_RANGE.map((r) => (
                  <Pressable key={r} style={[styles.nwSegBtn, nwVisual === r && styles.nwSegOn]} onPress={() => setNwVisual(r)}>
                    <Text style={[styles.nwSegTxt, nwVisual === r && styles.nwSegTxtOn]}>{r}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
            <View style={styles.chartMock}>
              <View style={styles.chartFill} />
              <View style={styles.chartLine} />
            </View>
            <Text style={styles.chartCaption}>Net worth over time</Text>
          </View>

          <View style={styles.assetsCard}>
            <Text style={styles.assetsK}>Total assets</Text>
            <Text style={styles.assetsHuge}>{fmtMoneyBig(assetsTotal)}</Text>
            {assetLines.length ? (
              assetLines.map((row, i) => (
                <View key={row.label} style={[styles.assetRow, i < assetLines.length - 1 && styles.assetRowRule]}>
                  <Text style={styles.assetRowLbl}>{row.label}</Text>
                  <Text style={styles.assetRowAmt}>{fmtMoneyBig(row.val)}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.mutedMini}>No asset breakdown yet.</Text>
            )}
            <MaterialCommunityIcons
              name="bank-outline"
              size={120}
              color="rgba(255,255,255,0.06)"
              style={styles.assetsWatermark}
            />
          </View>

          <View style={styles.liabCard}>
            <Text style={styles.liabK}>Total liabilities</Text>
            <Text style={styles.liabHuge}>{fmtMoneyBig(liabilitiesTotal)}</Text>
            {liabilityLines.length ? (
              liabilityLines.map((row) => (
                <View key={row.label} style={styles.liabRow}>
                  <View style={styles.liabLeft}>
                    <View style={[styles.liabDot, { backgroundColor: row.dot }]} />
                    <Text style={styles.liabRowLbl}>{row.label}</Text>
                  </View>
                  <Text style={styles.liabRowAmt}>{fmtMoneyBig(row.val)}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.mutedText}>No liability lines.</Text>
            )}
            <View style={styles.ratioRow}>
              <Text style={styles.ratioK}>Debt-to-asset ratio</Text>
              <Text style={styles.ratioV}>{debtToAssetPct === null ? "—" : `${debtToAssetPct.toFixed(1)}%`}</Text>
            </View>
          </View>

          <View style={styles.metricsRow}>
            <View style={styles.metricCard}>
              <View style={[styles.metricIcon, { backgroundColor: theme.colors.primaryContainer }]}>
                <MaterialCommunityIcons name="chart-line" size={26} color={theme.colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.metricK}>Investment ROI</Text>
                <Text style={styles.metricVal}>—</Text>
                <Text style={styles.metricSub}>Trailing view (connect investments)</Text>
              </View>
            </View>
            <View style={styles.metricCard}>
              <View style={[styles.metricIcon, { backgroundColor: theme.colors.tertiaryContainer }]}>
                <MaterialCommunityIcons name="wallet-outline" size={26} color={theme.colors.tertiary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.metricK}>Net cash flow</Text>
                <Text style={styles.metricVal}>
                  {avgMonthlyFlow === null
                    ? "—"
                    : `${avgMonthlyFlow >= 0 ? "+" : "-"}${fmtMoney(Math.abs(avgMonthlyFlow))}`}
                </Text>
                <Text style={styles.metricSub}>Scaled to ~30 days</Text>
              </View>
            </View>
            <View style={styles.metricCard}>
              <View style={[styles.metricIcon, { backgroundColor: theme.colors.secondaryContainer }]}>
                <MaterialCommunityIcons name="shield-check-outline" size={26} color={theme.colors.secondary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.metricK}>Liquidity score</Text>
                <Text style={styles.metricVal}>{liquidityLabel}</Text>
                <Text style={styles.metricSub}>Assets vs liabilities</Text>
              </View>
            </View>
          </View>
        </>
      )}

      <Text style={styles.sectionHead}>Spending overview</Text>
      <Text style={styles.sectionSub}>Cashflow for the selected window</Text>
      <View style={styles.pickerRow}>
        {CASHFLOW_DAYS.map((d) => (
          <Pressable key={d} style={[styles.pill, days === d ? styles.pillActive : null]} onPress={() => setDays(d)}>
            <Text style={[styles.pillText, days === d ? styles.pillTextActive : null]}>{d} days</Text>
          </Pressable>
        ))}
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.cardLabel}>Income</Text>
            <Text style={styles.cardValue}>{fmtMoney(data?.income_total)}</Text>
            <Text style={styles.cardLabel}>Expenses</Text>
            <Text style={styles.cardValue}>{fmtMoney(data?.expense_total)}</Text>
            <Text style={styles.cardLabel}>Net</Text>
            <Text
              style={[
                styles.cardValue,
                { color: toNumber(data?.net) !== null && (toNumber(data?.net) as number) >= 0 ? "#16a34a" : "#dc2626" },
              ]}
            >
              {fmtMoney(data?.net)}
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Top spending categories</Text>
            {(topCategories.length ? topCategories : []).map((c, idx) => (
              <View key={`${String(c.category_code ?? idx)}`} style={styles.row}>
                <Text style={styles.rowLabel} numberOfLines={1}>
                  {c.label ?? `Category ${c.category_code ?? "—"}`}
                </Text>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.rowAmount}>{fmtMoney(c.total)}</Text>
                  <Text style={styles.rowMeta}>{c.count ? `${c.count} items` : "—"}</Text>
                </View>
              </View>
            ))}
            {topCategories.length === 0 ? <Text style={styles.mutedText}>No spending data.</Text> : null}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: theme.colors.background },
  appBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  appBarLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  av: {
    width: 32,
    height: 32,
    borderRadius: 999,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  avTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 14 },
  brand: { fontSize: 20, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  execK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  bigTitle: {
    fontSize: 28,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginTop: 4,
    marginBottom: 12,
  },
  actionRow: { flexDirection: "row", gap: 10, marginBottom: 8 },
  outlineBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: theme.radii.lg,
    paddingVertical: 12,
    backgroundColor: theme.colors.surface,
  },
  outlineBtnTxt: { fontSize: 11, fontFamily: "Inter_800ExtraBold", letterSpacing: 0.8, textTransform: "uppercase" },
  fillBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderRadius: theme.radii.lg,
    paddingVertical: 12,
    backgroundColor: theme.colors.primary,
  },
  fillBtnTxt: { fontSize: 11, fontFamily: "Inter_800ExtraBold", letterSpacing: 0.8, color: theme.colors.onPrimary, textTransform: "uppercase" },
  nwCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
    overflow: "hidden",
  },
  nwTopRow: { gap: 10, marginBottom: 16 },
  nwK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  nwHuge: { fontSize: 32, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 6 },
  trendRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  trendTxt: { fontSize: 13, fontFamily: "Inter_700Bold", color: "#059669" },
  nwSeg: { flexDirection: "row", backgroundColor: theme.colors.surfaceContainer, borderRadius: 10, padding: 4, gap: 4, marginTop: 8 },
  nwSegBtn: { flex: 1, paddingVertical: 8, borderRadius: 8, alignItems: "center" },
  nwSegOn: { backgroundColor: theme.colors.surface, ...theme.shadows.sm },
  nwSegTxt: { fontSize: 10, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary },
  nwSegTxtOn: { color: theme.colors.primary },
  chartMock: {
    height: 120,
    borderRadius: 16,
    backgroundColor: `${theme.colors.primary}12`,
    marginTop: 8,
    overflow: "hidden",
    justifyContent: "flex-end",
  },
  chartFill: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    height: "70%",
    backgroundColor: `${theme.colors.primary}18`,
    borderTopLeftRadius: 40,
    borderTopRightRadius: 40,
  },
  chartLine: {
    height: 4,
    marginHorizontal: 12,
    marginBottom: 16,
    borderRadius: 4,
    backgroundColor: theme.colors.primary,
    opacity: 0.9,
  },
  chartCaption: { marginTop: 12, fontSize: 13, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  assetsCard: {
    backgroundColor: "#1e1b4b",
    borderRadius: 24,
    padding: 20,
    overflow: "hidden",
    position: "relative",
  },
  assetsK: { fontSize: 10, fontFamily: "Inter_800ExtraBold", color: "#a5b4fc", letterSpacing: 2, textTransform: "uppercase" },
  assetsHuge: { fontSize: 28, fontFamily: "Inter_800ExtraBold", color: "#fff", marginTop: 6, marginBottom: 12 },
  assetRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 10 },
  assetRowRule: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "rgba(255,255,255,0.12)" },
  assetRowLbl: { fontSize: 13, fontFamily: "Inter_600SemiBold", color: "rgba(255,255,255,0.72)" },
  assetRowAmt: { fontSize: 13, fontFamily: "Inter_800ExtraBold", color: "#fff" },
  assetsWatermark: { position: "absolute", right: -16, bottom: -24 },
  liabCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  liabK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  liabHuge: { fontSize: 28, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 6, marginBottom: 8 },
  liabRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 10 },
  liabLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  liabDot: { width: 8, height: 8, borderRadius: 4 },
  liabRowLbl: { fontSize: 13, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurfaceVariant },
  liabRowAmt: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  ratioRow: {
    marginTop: 12,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: theme.colors.outlineVariant,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  ratioK: { fontSize: 11, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary, letterSpacing: 1 },
  ratioV: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  metricsRow: { gap: 10 },
  metricCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: theme.colors.surface,
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  metricIcon: { width: 56, height: 56, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  metricK: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  metricVal: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 4 },
  metricSub: { fontSize: 11, fontFamily: "Inter_400Regular", color: theme.colors.onSurfaceVariant, marginTop: 4 },
  sectionHead: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 8 },
  sectionSub: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.secondary },
  mutedMini: { fontSize: 12, color: "rgba(255,255,255,0.6)", fontFamily: "Inter_400Regular" },
  pickerRow: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  pill: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: "#fff" },
  pillActive: { borderColor: "#135bec", backgroundColor: "#dbeafe" },
  pillText: { fontWeight: "900", color: "#0f172a", fontSize: 13 },
  pillTextActive: { color: "#135bec" },
  card: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, gap: 6, backgroundColor: "#fff" },
  cardLabel: { fontSize: 12, fontWeight: "900", color: "#64748b", marginTop: 6 },
  cardValue: { fontSize: 20, fontWeight: "900", color: "#0f172a", marginBottom: 4 },
  sectionTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a", marginBottom: 10 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#f1f5f9" },
  rowLabel: { flex: 1, fontSize: 13, fontWeight: "900", color: "#0f172a" },
  rowAmount: { fontSize: 13, fontWeight: "900", color: "#16a34a" },
  rowMeta: { fontSize: 11, fontWeight: "900", color: "#64748b", marginTop: 2 },
  mutedText: { color: "#64748b" },
  errorText: { color: "#dc2626" },
});
