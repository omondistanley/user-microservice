import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

type Summary = {
  net_worth?: number | string;
  assets_total?: number | string;
  liabilities_total?: number | string;
  assets?: Record<string, number | string>;
  liabilities?: Record<string, number | string>;
  warnings?: string[];
};

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const TABS = ["1M", "6M", "1Y", "ALL"] as const;

export default function NetWorthScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<Summary | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]>("1M");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/summary`, {
          method: "GET",
        });
        const json = (await res.json().catch(() => null)) as Summary | null;
        if (!res.ok) {
          throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to load net worth.");
        }
        if (cancelled) return;
        setData(json);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load net worth.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const nw = toNumber(data?.net_worth);
  const assetsT = toNumber(data?.assets_total);
  const liabT = toNumber(data?.liabilities_total);

  const insightCopy = useMemo(() => {
    const w = data?.warnings?.[0];
    if (w) return w;
    if (nw === null) return "Net worth updates as you connect accounts and add manual balances.";
    return `Assets total ${fmtMoney(assetsT)} vs liabilities ${fmtMoney(liabT)} from your latest synced data.`;
  }, [data, nw, assetsT, liabT]);

  return (
    <View style={[styles.root, { paddingTop: insets.top, backgroundColor: theme.colors.surfaceDim }]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="chevron-left" size={28} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Net Worth</Text>
        <Pressable hitSlop={12} onPress={() => router.push("/more")}>
          <MaterialCommunityIcons name="menu" size={24} color={theme.colors.onSurface} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.kicker}>Total net worth</Text>
        <Text style={styles.hero}>{fmtMoney(data?.net_worth)}</Text>

        <View style={styles.trendPill}>
          <MaterialCommunityIcons name="trending-up" size={16} color="#16a34a" />
          <Text style={styles.trendTxt}>Live summary from gateway</Text>
        </View>

        <View style={styles.tabs}>
          {TABS.map((t) => (
            <Pressable key={t} style={[styles.tab, tab === t && styles.tabOn]} onPress={() => setTab(t)}>
              <Text style={[styles.tabTxt, tab === t && styles.tabTxtOn]}>{t}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.chartCard}>
          <MaterialCommunityIcons
            name="chart-bell-curve"
            size={120}
            color={`${theme.colors.outline}44`}
            style={styles.watermark}
          />
          <Text style={styles.chartHint}>
            Historical chart uses account sync depth; {tab} view is informational here.
          </Text>
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <>
            <View style={styles.row2}>
              <View style={styles.tile}>
                <View style={[styles.tileIcon, { backgroundColor: theme.colors.primary }]}>
                  <MaterialCommunityIcons name="wallet" size={18} color={theme.colors.onPrimary} />
                </View>
                <Text style={styles.tileK}>Total assets</Text>
                <Text style={styles.tileV}>{fmtMoney(assetsT)}</Text>
              </View>
              <View style={styles.tile}>
                <View style={[styles.tileIcon, { backgroundColor: theme.colors.secondary }]}>
                  <MaterialCommunityIcons name="cash-remove" size={18} color={theme.colors.onPrimary} />
                </View>
                <Text style={styles.tileK}>Liabilities</Text>
                <Text style={styles.tileV}>{fmtMoney(liabT)}</Text>
              </View>
            </View>

            <Text style={styles.section}>Insights</Text>
            <View style={styles.insight}>
              <View style={[styles.insDot, { backgroundColor: "#dcfce7" }]}>
                <MaterialCommunityIcons name="arrow-up-bold" size={18} color="#166534" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.insTitle}>Snapshot</Text>
                <Text style={styles.insBody}>{insightCopy}</Text>
              </View>
            </View>

            <View style={styles.insight}>
              <View style={[styles.insDot, { backgroundColor: theme.colors.primaryContainer }]}>
                <MaterialCommunityIcons name="lightbulb-outline" size={18} color={theme.colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.insTitle}>Breakdown</Text>
                <Text style={styles.insBody}>
                  View manual assets and liabilities from the detailed breakdown screen.
                </Text>
              </View>
            </View>

            <Pressable style={styles.btn} onPress={() => router.push("/net-worth/breakdown")}>
              <Text style={styles.btnTxt}>Open asset & liability breakdown</Text>
              <MaterialCommunityIcons name="chevron-right" size={22} color={theme.colors.onPrimary} />
            </Pressable>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  headerTitle: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  scroll: { paddingHorizontal: theme.spacing.xl, paddingTop: 20 },
  kicker: {
    textAlign: "center",
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  hero: {
    textAlign: "center",
    fontSize: 36,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.inverseSurface,
    marginTop: 8,
  },
  trendPill: {
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 12,
    backgroundColor: "#dcfce7",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
  },
  trendTxt: { fontSize: 13, fontFamily: "Inter_700Bold", color: "#166534" },
  tabs: {
    flexDirection: "row",
    marginTop: 20,
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: 999,
    padding: 4,
  },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 999, alignItems: "center" },
  tabOn: { backgroundColor: theme.colors.surface, ...theme.shadows.sm },
  tabTxt: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.secondary },
  tabTxtOn: { color: theme.colors.onSurface },
  chartCard: {
    marginTop: 16,
    height: 160,
    borderRadius: theme.radii.xl,
    backgroundColor: theme.colors.primaryFixed,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    overflow: "hidden",
    justifyContent: "flex-end",
    padding: 16,
  },
  watermark: { position: "absolute", alignSelf: "center", top: 20, opacity: 0.35 },
  chartHint: { fontSize: 12, fontFamily: "Inter_400Regular", color: theme.colors.onPrimaryContainer, zIndex: 1 },
  row2: { flexDirection: "row", gap: 12, marginTop: 20 },
  tile: {
    flex: 1,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  tileIcon: {
    width: 36,
    height: 36,
    borderRadius: theme.radii.sm,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 10,
  },
  tileK: { fontSize: 10, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary, letterSpacing: 1 },
  tileV: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, marginTop: 6 },
  section: { marginTop: 28, fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  insight: {
    flexDirection: "row",
    gap: 12,
    marginTop: 14,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    alignItems: "flex-start",
  },
  insDot: {
    width: 40,
    height: 40,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
  },
  insTitle: { fontSize: 15, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  insBody: { marginTop: 4, fontSize: 13, fontFamily: "Inter_400Regular", color: theme.colors.secondary, lineHeight: 18 },
  btn: {
    marginTop: 20,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    paddingHorizontal: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  btnTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 15, flex: 1 },
  error: { color: theme.colors.error, marginTop: 12, fontFamily: "Inter_600SemiBold" },
});
