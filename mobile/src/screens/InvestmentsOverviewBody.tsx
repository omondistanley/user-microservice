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
import { GATEWAY_BASE_URL } from "../config";
import { authClient } from "../authClient";
import { theme } from "../theme";

export type PortfolioValueResponse = {
  total_market_value?: number | string;
  total_cost_basis?: number | string;
  unrealized_pl?: number | string;
  positions?: Array<{
    symbol?: string;
    quantity?: number | string;
    avg_cost?: number | string;
    currency?: string;
    cost_basis?: number | string;
    market_value?: number | string;
  }>;
};

type HealthResponse = {
  headline?: string;
  score?: number;
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

const HOLDING_ACCENTS = [
  { tile: "#dbeafe", ink: theme.colors.primary },
  { tile: "#f1f5f9", ink: "#64748b" },
  { tile: "#fef9c3", ink: "#a16207" },
  { tile: "#ede9fe", ink: "#6d28d9" },
  { tile: "#ffedd5", ink: "#c2410c" },
];

const RANGE_OPTIONS = ["1W", "1M", "3M", "1Y", "ALL"] as const;

function bucketForSymbol(sym: string): "stocks" | "crypto" | "bonds" | "cash" {
  const s = sym.toUpperCase();
  if (/(BTC|ETH|SOL|CRYPTO)/.test(s)) return "crypto";
  if (/(CASH|SPAXX|FDRXX|BIL|SGOV)/.test(s)) return "cash";
  if (/(BND|AGG|TLT|LQD|BOND)/.test(s)) return "bonds";
  return "stocks";
}

export function InvestmentsOverviewBody({ stackMode = false }: { stackMode?: boolean }) {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<PortfolioValueResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [meInitial, setMeInitial] = useState("•");
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]>("1W");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [portRes, healthRes, meRes] = await Promise.all([
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/value`, {
            method: "GET",
          }),
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/health`, {
            method: "GET",
          }),
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/user/me`, { method: "GET" }),
        ]);
        const portJson = (await portRes.json().catch(() => null)) as PortfolioValueResponse | null;
        if (!portRes.ok) {
          throw new Error(
            (portJson as any)?.detail ? String((portJson as any).detail) : "Failed to load investments.",
          );
        }
        if (cancelled) return;
        setData(portJson);
        if (healthRes.ok) {
          const h = (await healthRes.json().catch(() => null)) as HealthResponse;
          setHealth(h);
        } else {
          setHealth(null);
        }
        if (meRes.ok) {
          const m = await meRes.json().catch(() => null);
          const fn = m?.first_name?.trim?.();
          const em = m?.email?.trim?.();
          const ch = fn ? fn.charAt(0) : em ? em.charAt(0) : "•";
          setMeInitial(String(ch).toUpperCase());
        }
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load investments.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalMv = toNumber(data?.total_market_value);
  const costBasis = toNumber(data?.total_cost_basis);
  const unrealized = toNumber(data?.unrealized_pl);

  const ytdLabel = useMemo(() => {
    if (costBasis !== null && costBasis > 0 && unrealized !== null) {
      const pct = (unrealized / costBasis) * 100;
      const sign = pct >= 0 ? "+" : "";
      return `${sign}${pct.toFixed(1)}% vs cost basis`;
    }
    if (unrealized !== null) {
      const sign = unrealized >= 0 ? "+" : "";
      return `${sign}${fmtMoney(unrealized)} unrealized`;
    }
    return "Performance tracking";
  }, [costBasis, unrealized]);

  const ytdPositive = unrealized === null ? true : unrealized >= 0;

  const allocation = useMemo(() => {
    const positions = data?.positions ?? [];
    const total = toNumber(data?.total_market_value) ?? 0;
    const rows = positions
      .map((p) => ({
        symbol: String(p?.symbol ?? "—"),
        mv: toNumber(p?.market_value) ?? 0,
      }))
      .filter((r) => r.mv > 0)
      .sort((a, b) => b.mv - a.mv);

    if (!total || rows.length === 0) {
      return {
        segments: [] as { label: string; pct: number; color: string }[],
        centerPct: 0,
        centerLabel: "Holdings",
      };
    }

    const palette = ["#ffffff", "rgba(255,255,255,0.75)", "rgba(255,255,255,0.55)", "rgba(255,255,255,0.35)"];
    const top = rows.slice(0, 4);
    const restMv = rows.slice(4).reduce((s, r) => s + r.mv, 0);
    const segments = top.map((r, i) => ({
      label: r.symbol,
      pct: Math.round((r.mv / total) * 100),
      color: palette[i % palette.length],
    }));
    if (restMv > 0) {
      segments.push({
        label: "Other",
        pct: Math.max(0, 100 - segments.reduce((s, x) => s + x.pct, 0)),
        color: "rgba(255,255,255,0.2)",
      });
    }
    const centerPct = segments[0]?.pct ?? 0;
    const centerLabel = segments[0]?.label ?? "Top";
    return { segments, centerPct, centerLabel };
  }, [data]);

  const bars = useMemo(() => {
    const t = totalMv ?? 0;
    const seed = Math.max(1, Math.floor(t % 97) || 3);
    return [0.4, 0.55, 0.5, 0.72, 0.65, 0.88, 1].map((h, i) => ({
      h: Math.min(1, h * (0.85 + ((seed + i * 7) % 10) / 100)),
    }));
  }, [totalMv]);

  const bucketAlloc = useMemo(() => {
    const positions = data?.positions ?? [];
    const total = toNumber(data?.total_market_value) ?? 0;
    const sums = { stocks: 0, crypto: 0, bonds: 0, cash: 0 };
    for (const p of positions) {
      const sym = String(p?.symbol ?? "");
      const mv = toNumber(p?.market_value) ?? 0;
      const b = bucketForSymbol(sym);
      sums[b] += mv;
    }
    if (total <= 0) {
      return [
        { key: "stocks" as const, label: "Stocks", pct: 0, color: theme.colors.primary },
        { key: "crypto" as const, label: "Crypto", pct: 0, color: theme.colors.tertiary },
        { key: "bonds" as const, label: "Bonds", pct: 0, color: theme.colors.primaryFixed },
        { key: "cash" as const, label: "Cash", pct: 0, color: "#16a34a" },
      ];
    }
    return [
      { key: "stocks" as const, label: "Stocks", pct: Math.round((sums.stocks / total) * 100), color: theme.colors.primary },
      { key: "crypto" as const, label: "Crypto", pct: Math.round((sums.crypto / total) * 100), color: theme.colors.tertiary },
      { key: "bonds" as const, label: "Bonds", pct: Math.round((sums.bonds / total) * 100), color: theme.colors.primaryFixed },
      { key: "cash" as const, label: "Cash", pct: Math.round((sums.cash / total) * 100), color: "#16a34a" },
    ];
  }, [data]);

  const positionsSorted = useMemo(() => {
    const positions = data?.positions ?? [];
    const total = toNumber(data?.total_market_value) ?? 0;
    return [...positions]
      .map((p, idx) => {
        const mv = toNumber(p?.market_value);
        const cb = toNumber(p?.cost_basis);
        const pctMv = total > 0 && mv !== null ? (mv / total) * 100 : 0;
        const plPct =
          cb !== null && cb > 0 && mv !== null ? ((mv - cb) / cb) * 100 : null;
        return {
          key: `${String(p?.symbol ?? "p")}-${idx}`,
          symbol: String(p?.symbol ?? "—"),
          mv,
          plPct,
          allocPct: pctMv,
          accent: HOLDING_ACCENTS[idx % HOLDING_ACCENTS.length],
        };
      })
      .sort((a, b) => (b.mv ?? 0) - (a.mv ?? 0));
  }, [data]);

  const insightTitle =
    health?.headline && String(health.headline).trim()
      ? String(health.headline)
      : "Keep tracking your allocation";
  const insightBody =
    typeof health?.score === "number"
      ? `Portfolio health score ${Math.round(health.score)}/100. Revisit recommendations as your holdings change.`
      : "Connect holdings or add positions to unlock tailored portfolio guidance.";

  if (loading) {
    return (
      <View style={{ paddingVertical: 40 }}>
        <ActivityIndicator color={theme.colors.primary} />
      </View>
    );
  }
  if (error) {
    return <Text style={styles.errorText}>{error}</Text>;
  }

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      {!stackMode ? (
        <View
          style={[
            styles.topBar,
            {
              paddingTop: insets.top + 8,
              paddingBottom: 10,
              borderBottomWidth: 1,
              borderBottomColor: theme.colors.outlineVariant,
            },
          ]}
        >
          <View style={styles.topBarLeft}>
            <View style={styles.avatarSm}>
              <Text style={styles.avatarSmText}>{meInitial}</Text>
            </View>
            <Text style={styles.brandTitle}>PocketII</Text>
          </View>
          <Pressable hitSlop={12} onPress={() => router.push("/notifications")}>
            <MaterialCommunityIcons name="bell-outline" size={24} color={theme.colors.primary} />
          </Pressable>
        </View>
      ) : (
        <View style={{ height: 8 }} />
      )}

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: insets.bottom + (stackMode ? 24 : 100) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.bluePanel}>
          <Text style={styles.panelKicker}>Total investment balance</Text>
          <View style={styles.panelValueRow}>
            <Text style={styles.panelValue}>{fmtMoney(data?.total_market_value)}</Text>
            <View style={styles.inlinePill}>
              <Text style={styles.inlinePillTxt}>{ytdLabel}</Text>
            </View>
          </View>
          <View style={styles.ytdPill}>
            <MaterialCommunityIcons
              name={ytdPositive ? "trending-up" : "trending-down"}
              size={16}
              color={theme.colors.primaryFixedDim}
            />
            <Text style={styles.ytdText}>{range} view</Text>
          </View>

          <View style={styles.sparkRow}>
            {bars.map((b, i) => (
              <View key={i} style={styles.sparkCol}>
                <View style={[styles.sparkBar, { height: `${Math.round(b.h * 100)}%` }]} />
              </View>
            ))}
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rangeRow}>
            {RANGE_OPTIONS.map((r) => (
              <Pressable key={r} style={[styles.rangeChip, range === r && styles.rangeChipOn]} onPress={() => setRange(r)}>
                <Text style={[styles.rangeTxt, range === r && styles.rangeTxtOn]}>{r}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={[styles.panelKicker, { marginTop: 20 }]}>Asset allocation breakdown</Text>
          <View style={styles.donutWrap}>
            <View style={styles.donutRing} />
            <View style={[styles.donutArc, { borderTopColor: "#ffffff", borderRightColor: "transparent" }]} />
            <View style={styles.donutCenter}>
              <Text style={styles.donutPct}>{allocation.centerPct}%</Text>
              <Text style={styles.donutSub}>{allocation.centerLabel}</Text>
            </View>
          </View>

          <View style={{ gap: 12 }}>
            {allocation.segments.length === 0 ? (
              <Text style={styles.legendMuted}>No allocation data yet.</Text>
            ) : (
              allocation.segments.map((s) => (
                <View key={s.label} style={styles.legendRow}>
                  <View style={styles.legendLeft}>
                    <View style={[styles.legendDot, { backgroundColor: s.color }]} />
                    <Text style={styles.legendLabel}>{s.label}</Text>
                  </View>
                  <Text style={styles.legendPct}>{s.pct}%</Text>
                </View>
              ))
            )}
          </View>

          <Pressable
            style={styles.reportBtn}
            onPress={() => router.push("/reports")}
          >
            <Text style={styles.reportBtnText}>Generate Performance Report</Text>
          </Pressable>
        </View>

        <View style={styles.lower}>
          <Text style={styles.allocTitle}>Asset allocation</Text>
          <View style={styles.allocGrid}>
            {bucketAlloc.map((b) => (
              <View key={b.key} style={styles.allocCard}>
                <View style={styles.allocCardTop}>
                  <Text style={styles.allocLabel}>{b.label}</Text>
                  <Text style={[styles.allocPct, { color: b.color }]}>{b.pct}%</Text>
                </View>
                <View style={styles.allocTrack}>
                  <View style={[styles.allocFill, { width: `${Math.min(100, b.pct)}%`, backgroundColor: b.color }]} />
                </View>
              </View>
            ))}
          </View>

          <View style={styles.holdingsHeader}>
            <View style={{ flex: 1 }}>
              <Text style={styles.holdingsTitle}>Top Holdings</Text>
              <Text style={styles.holdingsSub}>Institutional grade analysis & tracking</Text>
            </View>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <View style={styles.iconBtn}>
                <MaterialCommunityIcons name="filter-variant" size={22} color={theme.colors.onSurface} />
              </View>
              <View style={styles.iconBtn}>
                <MaterialCommunityIcons name="magnify" size={22} color={theme.colors.onSurface} />
              </View>
            </View>
          </View>

          {positionsSorted.length === 0 ? (
            <Text style={styles.legendMuted}>No holdings yet.</Text>
          ) : (
            positionsSorted.map((p) => {
              const pl = p.plPct;
              const up = pl === null || pl >= 0;
              return (
                <View key={p.key} style={styles.holdingCard}>
                  <View style={styles.holdingTop}>
                    <View style={styles.holdingLeft}>
                      <View style={[styles.holdingIcon, { backgroundColor: p.accent.tile }]}>
                        <MaterialCommunityIcons name="domain" size={22} color={p.accent.ink} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.holdingName} numberOfLines={1}>
                          {p.symbol}
                        </Text>
                        <Text style={styles.holdingMeta}>Equity • USD</Text>
                      </View>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={styles.holdingMv}>{fmtMoney(p.mv)}</Text>
                      {pl !== null ? (
                        <View style={styles.plRow}>
                          <MaterialCommunityIcons
                            name={up ? "arrow-up" : "arrow-down"}
                            size={14}
                            color={up ? "#16a34a" : theme.colors.error}
                          />
                          <Text style={[styles.plText, { color: up ? "#16a34a" : theme.colors.error }]}>
                            {Math.abs(pl).toFixed(1)}%
                          </Text>
                        </View>
                      ) : null}
                    </View>
                  </View>
                  <Text style={styles.allocFooter}>
                    {p.allocPct.toFixed(1)}% allocation
                  </Text>
                </View>
              );
            })
          )}

          <View style={styles.insightHeadRow}>
            <Text style={styles.insightSectionTitle}>Institutional Insights</Text>
            <Pressable onPress={() => router.push("/recommendations")}>
              <Text style={styles.recLink}>View Recommendations</Text>
            </Pressable>
          </View>
          <View style={styles.insightCard}>
            <MaterialCommunityIcons name="lightbulb-on-outline" size={28} color={theme.colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.insightCardTitle}>{insightTitle}</Text>
              <Text style={styles.insightCardBody}>{insightBody}</Text>
            </View>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.xl,
    backgroundColor: theme.colors.surface,
  },
  topBarLeft: { flexDirection: "row", alignItems: "center", gap: 12 },
  avatarSm: {
    width: 40,
    height: 40,
    borderRadius: 999,
    backgroundColor: theme.colors.secondaryFixed,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarSmText: { fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  brandTitle: {
    fontSize: 22,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: -0.5,
  },
  scrollContent: { flexGrow: 1 },
  bluePanel: {
    backgroundColor: theme.colors.primary,
    paddingHorizontal: theme.spacing.xl,
    paddingTop: theme.spacing.xxl,
    paddingBottom: theme.spacing.xxl,
    borderBottomLeftRadius: theme.radii.xl,
    borderBottomRightRadius: theme.radii.xl,
  },
  panelKicker: {
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: "rgba(255,255,255,0.8)",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  panelValueRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    marginTop: 8,
    flexWrap: "wrap",
  },
  panelValue: {
    fontSize: 30,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
    letterSpacing: -1,
    flexShrink: 1,
  },
  inlinePill: {
    backgroundColor: "rgba(255,255,255,0.2)",
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
  },
  inlinePillTxt: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
  },
  sparkRow: {
    flexDirection: "row",
    alignItems: "flex-end",
    height: 64,
    gap: 4,
    marginTop: 16,
  },
  sparkCol: { flex: 1, height: "100%", justifyContent: "flex-end" },
  sparkBar: {
    width: "100%",
    backgroundColor: "rgba(255,255,255,0.35)",
    borderTopLeftRadius: 4,
    borderTopRightRadius: 4,
    minHeight: 8,
  },
  rangeRow: { flexDirection: "row", gap: 8, marginTop: 14, paddingVertical: 4 },
  rangeChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.15)",
  },
  rangeChipOn: { backgroundColor: theme.colors.surface },
  rangeTxt: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: "rgba(255,255,255,0.75)" },
  rangeTxtOn: { color: theme.colors.primary },
  ytdPill: {
    marginTop: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.12)",
  },
  ytdText: {
    fontSize: 13,
    fontFamily: "Inter_700Bold",
    color: theme.colors.primaryFixedDim,
  },
  donutWrap: {
    width: 200,
    height: 200,
    alignSelf: "center",
    marginVertical: 24,
    alignItems: "center",
    justifyContent: "center",
  },
  donutRing: {
    position: "absolute",
    width: 200,
    height: 200,
    borderRadius: 100,
    borderWidth: 22,
    borderColor: "rgba(255,255,255,0.12)",
  },
  donutArc: {
    position: "absolute",
    width: 200,
    height: 200,
    borderRadius: 100,
    borderWidth: 22,
    borderBottomColor: "transparent",
    borderLeftColor: "transparent",
    transform: [{ rotate: "-35deg" }],
  },
  donutCenter: {
    alignItems: "center",
    justifyContent: "center",
  },
  donutPct: {
    fontSize: 32,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onPrimary,
  },
  donutSub: {
    marginTop: 4,
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: "rgba(255,255,255,0.6)",
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  legendRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  legendLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendLabel: { fontSize: 14, fontFamily: "Inter_600SemiBold", color: theme.colors.onPrimary },
  legendPct: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimary },
  legendMuted: { fontSize: 14, color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular" },
  reportBtn: {
    marginTop: 28,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    alignItems: "center",
    ...theme.shadows.md,
  },
  reportBtnText: {
    fontSize: 16,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
  },
  lower: {
    paddingHorizontal: theme.spacing.xl,
    paddingTop: theme.spacing.xxl,
    backgroundColor: theme.colors.surfaceContainerLow,
  },
  allocTitle: {
    fontSize: 18,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    marginBottom: 12,
  },
  allocGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginBottom: 8 },
  allocCard: {
    width: "47%",
    flexGrow: 1,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: 12,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  allocCardTop: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  allocLabel: { fontSize: 12, fontFamily: "Inter_500Medium", color: theme.colors.secondary },
  allocPct: { fontSize: 12, fontFamily: "Inter_800ExtraBold" },
  allocTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainerHigh,
    overflow: "hidden",
  },
  allocFill: { height: "100%", borderRadius: 999 },
  holdingsHeader: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 20,
    gap: 12,
  },
  holdingsTitle: {
    fontSize: 28,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: -0.5,
  },
  holdingsSub: {
    marginTop: 4,
    fontSize: 14,
    fontFamily: "Inter_400Regular",
    color: theme.colors.secondary,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.surface,
  },
  holdingCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    padding: theme.spacing.xl,
    marginBottom: 14,
  },
  holdingTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
  },
  holdingLeft: { flexDirection: "row", gap: 12, flex: 1, alignItems: "flex-start" },
  holdingIcon: {
    width: 48,
    height: 48,
    borderRadius: theme.radii.md,
    alignItems: "center",
    justifyContent: "center",
  },
  holdingName: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  holdingMeta: {
    marginTop: 4,
    fontSize: 11,
    fontFamily: "Inter_700Bold",
    color: theme.colors.secondary,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  holdingMv: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  plRow: { flexDirection: "row", alignItems: "center", gap: 2, marginTop: 4 },
  plText: { fontSize: 12, fontFamily: "Inter_800ExtraBold" },
  allocFooter: {
    marginTop: 14,
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  insightHeadRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 8,
    marginBottom: 12,
  },
  insightSectionTitle: {
    fontSize: 18,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
  },
  recLink: {
    fontSize: 13,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
  },
  insightCard: {
    flexDirection: "row",
    gap: 12,
    backgroundColor: theme.colors.primaryContainer,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.xl,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    marginBottom: 32,
  },
  insightCardTitle: {
    fontSize: 16,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
  },
  insightCardBody: {
    marginTop: 6,
    fontSize: 13,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onPrimaryContainer,
    opacity: 0.9,
  },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", padding: 20 },
});
