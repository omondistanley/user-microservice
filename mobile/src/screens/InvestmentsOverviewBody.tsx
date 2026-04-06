import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
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
import { gatewayJson, gatewayJsonOptional } from "../gatewayRequest";
import { useAppTheme, type AppTheme } from "../theme";
import { formatApiDetail } from "../formatApiDetail";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";

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
    source?: string;
    holding_id?: string | null;
  }>;
};

type GainsHistory = {
  dates?: string[];
  series?: {
    total?: { gain_loss?: number[] };
    manual?: { gain_loss?: number[] };
    alpaca?: { gain_loss?: number[] };
  };
  note?: string;
};

type AlpacaStatus = {
  connected?: boolean;
  is_paper?: boolean;
  last_sync_at?: string | null;
  alpaca_account_id?: string | null;
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

const RANGE_OPTIONS = ["1W", "1M", "3M", "1Y", "ALL"] as const;

function rangeToDays(r: (typeof RANGE_OPTIONS)[number]): number {
  switch (r) {
    case "1W":
      return 7;
    case "1M":
      return 30;
    case "3M":
      return 90;
    case "1Y":
      return 365;
    case "ALL":
      return 365;
    default:
      return 90;
  }
}

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
  const theme = useAppTheme();
  const styles = useMemo(() => createStyles(theme), [theme]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<PortfolioValueResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [range, setRange] = useState<(typeof RANGE_OPTIONS)[number]>("1W");
  const [refreshTick, setRefreshTick] = useState(0);
  const [gainsHistory, setGainsHistory] = useState<GainsHistory | null>(null);
  const [gainsLoading, setGainsLoading] = useState(false);
  const [gainsSeries, setGainsSeries] = useState<"total" | "manual" | "alpaca">("total");
  const [alpacaStatus, setAlpacaStatus] = useState<AlpacaStatus | null>(null);
  const [alpacaBusy, setAlpacaBusy] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [addSymbol, setAddSymbol] = useState("");
  const [addQty, setAddQty] = useState("");
  const [addCost, setAddCost] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [activeView, setActiveView] = useState<"overview" | "holdings">("overview");

  const holdingAccents = useMemo(
    () => [
      { tile: theme.colors.primaryContainer, ink: theme.colors.primary },
      { tile: theme.colors.secondaryContainer, ink: theme.colors.secondary },
      { tile: theme.colors.tertiaryContainer, ink: theme.colors.tertiary },
      { tile: theme.colors.surfaceContainerHigh, ink: theme.colors.onSurfaceVariant },
      { tile: theme.colors.surfaceContainerHighest, ink: theme.colors.onSurface },
    ],
    [theme],
  );

  const bumpRefresh = useCallback(() => setRefreshTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [portRes, healthRes, alpacaRes] = await Promise.all([
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/value`, {
            method: "GET",
          }),
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/portfolio/health`, {
            method: "GET",
          }),
          gatewayJsonOptional<AlpacaStatus>("/api/v1/alpaca/status", { method: "GET" }),
        ]);
        const portJson = (await portRes.json().catch(() => null)) as PortfolioValueResponse | null;
        if (!portRes.ok) {
          throw new Error(formatApiDetail((portJson as any)?.detail, "Failed to load investments."));
        }
        if (cancelled) return;
        setData(portJson);
        if (alpacaRes.ok && alpacaRes.data) {
          setAlpacaStatus(alpacaRes.data);
        } else {
          setAlpacaStatus({ connected: false });
        }
        if (healthRes.ok) {
          const h = (await healthRes.json().catch(() => null)) as HealthResponse;
          setHealth(h);
        } else {
          setHealth(null);
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
  }, [refreshTick]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setGainsLoading(true);
      try {
        const days = rangeToDays(range);
        const gh = await gatewayJson<GainsHistory>(
          `/api/v1/portfolio/gains-history?days=${encodeURIComponent(String(days))}`,
          { method: "GET" },
        );
        if (!cancelled) setGainsHistory(gh);
      } catch {
        if (!cancelled) setGainsHistory(null);
      } finally {
        if (!cancelled) setGainsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [range, refreshTick]);

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
  }, [data, theme]);

  const sparkHeights = useMemo(() => {
    const raw = gainsHistory?.series?.[gainsSeries]?.gain_loss;
    const gl = raw?.map((v) => Number(v)).filter((n) => Number.isFinite(n));
    if (gl && gl.length > 0) {
      const slice = gl.slice(-12);
      const min = Math.min(...slice);
      const max = Math.max(...slice);
      const span = max - min || 1;
      return slice.map((v) => ({
        h: Math.min(1, Math.max(0.08, 0.12 + 0.88 * ((v - min) / span))),
      }));
    }
    const t = totalMv ?? 0;
    const seed = Math.max(1, Math.floor(t % 97) || 3);
    return [0.4, 0.55, 0.5, 0.72, 0.65, 0.88, 1].map((h, i) => ({
      h: Math.min(1, h * (0.85 + ((seed + i * 7) % 10) / 100)),
    }));
  }, [gainsHistory, gainsSeries, totalMv]);

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
        { key: "cash" as const, label: "Cash", pct: 0, color: theme.colors.onTertiaryContainer },
      ];
    }
    return [
      { key: "stocks" as const, label: "Stocks", pct: Math.round((sums.stocks / total) * 100), color: theme.colors.primary },
      { key: "crypto" as const, label: "Crypto", pct: Math.round((sums.crypto / total) * 100), color: theme.colors.tertiary },
      { key: "bonds" as const, label: "Bonds", pct: Math.round((sums.bonds / total) * 100), color: theme.colors.primaryFixed },
      { key: "cash" as const, label: "Cash", pct: Math.round((sums.cash / total) * 100), color: theme.colors.onTertiaryContainer },
    ];
  }, [data]);

  const positionsSorted = useMemo(() => {
    const positions = data?.positions ?? [];
    const total = toNumber(data?.total_market_value) ?? 0;
    return [...positions]
      .map((p, idx) => {
        const mv = toNumber(p?.market_value);
        const cb = toNumber(p?.cost_basis);
        const qty = toNumber(p?.quantity);
        const pctMv = total > 0 && mv !== null ? (mv / total) * 100 : 0;
        const plPct =
          cb !== null && cb > 0 && mv !== null ? ((mv - cb) / cb) * 100 : null;
        const source = String(p?.source ?? "manual").toLowerCase();
        return {
          key: `${String(p?.holding_id ?? p?.symbol ?? "p")}-${idx}`,
          symbol: String(p?.symbol ?? "—"),
          mv,
          qty,
          plPct,
          allocPct: pctMv,
          source,
          holdingId: p?.holding_id ?? null,
          accent: holdingAccents[idx % holdingAccents.length],
        };
      })
      .sort((a, b) => (b.mv ?? 0) - (a.mv ?? 0));
  }, [data, holdingAccents]);

  const onAlpacaSync = async () => {
    setAlpacaBusy(true);
    try {
      await gatewayJson("/api/v1/alpaca/sync", { method: "POST" });
      const st = await gatewayJsonOptional<AlpacaStatus>("/api/v1/alpaca/status", { method: "GET" });
      if (st.ok && st.data) setAlpacaStatus(st.data);
      bumpRefresh();
    } catch (e: unknown) {
      Alert.alert("Sync failed", e instanceof Error ? e.message : "Alpaca sync failed.");
    } finally {
      setAlpacaBusy(false);
    }
  };

  const placeAlpacaOrder = async (symbol: string, qty: number, side: "buy" | "sell") => {
    await gatewayJson("/api/v1/alpaca/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: symbol.toUpperCase(),
        qty,
        side,
        type: "market",
      }),
    });
    await gatewayJson("/api/v1/alpaca/sync", { method: "POST" });
    bumpRefresh();
  };

  const onSellAlpaca = (symbol: string, qty: number) => {
    if (!alpacaStatus?.connected) {
      Alert.alert("Alpaca", "Connect Alpaca in Settings → Integrations first.");
      return;
    }
    if (!(qty > 0)) {
      Alert.alert("Sell", "Invalid quantity.");
      return;
    }
    Alert.alert(
      "Sell on Alpaca",
      `Place a market sell for ${qty} share(s) of ${symbol}?`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Sell",
          style: "destructive",
          onPress: async () => {
            try {
              await placeAlpacaOrder(symbol, qty, "sell");
            } catch (e: unknown) {
              Alert.alert("Order failed", e instanceof Error ? e.message : "Sell failed.");
            }
          },
        },
      ],
    );
  };

  const submitAddHolding = async () => {
    const sym = addSymbol.trim().toUpperCase();
    const qty = Number(String(addQty).replace(/,/g, ""));
    const cost = Number(String(addCost).replace(/,/g, ""));
    if (!sym || !Number.isFinite(qty) || qty <= 0) {
      Alert.alert("Add position", "Enter a valid symbol and positive quantity.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0) {
      Alert.alert("Add position", "Average cost must be zero or greater.");
      return;
    }
    setAddBusy(true);
    try {
      await gatewayJson("/api/v1/holdings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          quantity: qty,
          avg_cost: cost,
          currency: "USD",
          account_type: "taxable",
        }),
      });
      setAddOpen(false);
      setAddSymbol("");
      setAddQty("");
      setAddCost("");
      bumpRefresh();
      if (alpacaStatus?.connected) {
        Alert.alert(
          "Alpaca market buy?",
          `Also place a market buy on Alpaca for ${qty} share(s) of ${sym}? (Matches web flow after adding a holding.)`,
          [
            { text: "Skip", style: "cancel" },
            {
              text: "Place buy",
              onPress: async () => {
                try {
                  await placeAlpacaOrder(sym, qty, "buy");
                } catch (e: unknown) {
                  Alert.alert("Order failed", e instanceof Error ? e.message : "Buy failed.");
                }
              },
            },
          ],
        );
      }
    } catch (e: unknown) {
      Alert.alert("Add failed", e instanceof Error ? e.message : "Could not add holding.");
    } finally {
      setAddBusy(false);
    }
  };

  const insightTitle =
    health?.headline && String(health.headline).trim()
      ? String(health.headline)
      : "Keep tracking your allocation";
  const insightBody =
    typeof health?.score === "number"
      ? `Portfolio health score ${Math.round(health.score)}/100. Revisit recommendations as your holdings change.`
      : "Connect holdings or add positions to unlock tailored portfolio guidance.";

  const healthScore = typeof health?.score === "number" ? Math.max(0, Math.min(100, Math.round(health.score))) : null;
  const healthColor =
    healthScore === null ? "#94a3b8"
    : healthScore >= 70 ? "#16a34a"
    : healthScore >= 40 ? "#d97706"
    : "#dc2626";

  const [selectedHolding, setSelectedHolding] = useState<(typeof positionsSorted)[number] | null>(null);

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
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          {
            paddingTop: stackMode ? 8 : insets.top + 8,
            paddingBottom: insets.bottom + (stackMode ? 24 : 100),
          },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.viewSwitchRow}>
          <Pressable
            style={[styles.viewSwitchBtn, activeView === "overview" && styles.viewSwitchBtnOn]}
            onPress={() => setActiveView("overview")}
          >
            <Text style={[styles.viewSwitchTxt, activeView === "overview" && styles.viewSwitchTxtOn]}>Overview</Text>
          </Pressable>
          <Pressable
            style={[styles.viewSwitchBtn, activeView === "holdings" && styles.viewSwitchBtnOn]}
            onPress={() => setActiveView("holdings")}
          >
            <Text style={[styles.viewSwitchTxt, activeView === "holdings" && styles.viewSwitchTxtOn]}>Holdings</Text>
          </Pressable>
        </View>

        {activeView === "overview" ? (
        <View style={styles.bluePanel}>
          <Text style={styles.panelKicker}>Total investment balance</Text>
          <View style={styles.panelValueRow}>
            <Text style={styles.panelValue}>{fmtMoney(data?.total_market_value)}</Text>
            <View style={[styles.inlinePill, unrealized !== null && unrealized < 0 && { backgroundColor: "rgba(220,38,38,0.25)" }]}>
              <Text style={styles.inlinePillTxt}>{ytdLabel}</Text>
            </View>
          </View>
          {healthScore !== null ? (
            <View style={{ marginTop: 14, marginBottom: 4 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
                <Text style={[styles.panelKicker, { marginTop: 0, fontSize: 11 }]}>Portfolio health</Text>
                <Text style={{ fontSize: 13, fontWeight: "700", color: healthColor }}>{healthScore}/100</Text>
              </View>
              <View style={{ height: 6, borderRadius: 99, backgroundColor: "rgba(255,255,255,0.18)", overflow: "hidden" }}>
                <View style={{ width: `${healthScore}%`, height: "100%", borderRadius: 99, backgroundColor: healthColor }} />
              </View>
              {health?.headline ? (
                <Text style={[styles.panelKicker, { marginTop: 5, fontSize: 11, opacity: 0.85 }]} numberOfLines={1}>{health.headline}</Text>
              ) : null}
            </View>
          ) : null}
          <View style={styles.ytdPill}>
            <MaterialCommunityIcons
              name={ytdPositive ? "trending-up" : "trending-down"}
              size={16}
              color={theme.colors.primaryFixedDim}
            />
            <Text style={styles.ytdText}>
              {range} · gain/loss ({gainsSeries})
              {gainsLoading ? " · …" : ""}
            </Text>
          </View>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rangeRow}>
            {RANGE_OPTIONS.map((r) => (
              <Pressable key={r} style={[styles.rangeChip, range === r && styles.rangeChipOn]} onPress={() => setRange(r)}>
                <Text style={[styles.rangeTxt, range === r && styles.rangeTxtOn]}>{r}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={[styles.panelKicker, { marginTop: 12 }]}>P/L history (holdings × prices)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.rangeRow}>
            {(
              [
                { k: "total" as const, label: "Total" },
                { k: "manual" as const, label: "Manual" },
                { k: "alpaca" as const, label: "Alpaca" },
              ] as const
            ).map(({ k, label }) => (
              <Pressable
                key={k}
                style={[styles.rangeChip, gainsSeries === k && styles.rangeChipOn]}
                onPress={() => setGainsSeries(k)}
              >
                <Text style={[styles.rangeTxt, gainsSeries === k && styles.rangeTxtOn]}>{label}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <View style={styles.sparkRow}>
            {gainsLoading ? (
              <ActivityIndicator color={theme.colors.onPrimary} style={{ alignSelf: "center", flex: 1 }} />
            ) : (
              sparkHeights.map((b, i) => (
                <View key={i} style={styles.sparkCol}>
                  <View style={[styles.sparkBar, { height: `${Math.round(b.h * 100)}%` }]} />
                </View>
              ))
            )}
          </View>
          {gainsHistory?.note ? (
            <Text style={styles.gainsNote} numberOfLines={2}>
              {gainsHistory.note}
            </Text>
          ) : null}

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
              allocation.segments.map((s, segIdx) => (
                <View key={`alloc-legend-${segIdx}`} style={styles.legendRow}>
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
        ) : null}

        <View style={styles.lower}>
          {activeView === "overview" ? <Text style={styles.alpacaSectionK}>Alpaca brokerage</Text> : null}
          {activeView === "overview" ? (
          <View style={styles.alpacaCard}>
            {alpacaStatus?.connected ? (
              <>
                <View style={styles.alpacaRow}>
                  <MaterialCommunityIcons name="link-variant" size={22} color={theme.colors.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.alpacaTitle}>
                      Connected{alpacaStatus.is_paper === false ? " (live)" : " (paper)"}
                    </Text>
                    <Text style={styles.alpacaMeta}>
                      {alpacaStatus.alpaca_account_id ? `Account ${alpacaStatus.alpaca_account_id}` : "Account linked"}
                      {alpacaStatus.last_sync_at
                        ? ` · Last sync ${String(alpacaStatus.last_sync_at).slice(0, 19).replace("T", " ")}`
                        : ""}
                    </Text>
                  </View>
                </View>
                <View style={styles.alpacaActions}>
                  <Pressable
                    style={[styles.alpacaBtn, alpacaBusy && { opacity: 0.6 }]}
                    onPress={onAlpacaSync}
                    disabled={alpacaBusy}
                  >
                    <Text style={styles.alpacaBtnTxt}>{alpacaBusy ? "Syncing…" : "Sync positions"}</Text>
                  </Pressable>
                  <Pressable style={styles.alpacaBtnSecondary} onPress={() => router.push("/settings/integrations")}>
                    <Text style={styles.alpacaBtnSecondaryTxt}>Keys & disconnect</Text>
                  </Pressable>
                </View>
                <Text style={styles.alpacaHint}>
                  Alpaca-linked rows show a badge below. Use Sell for market sells; Add position can optionally place a
                  market buy after you save the lot.
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.alpacaTitle}>Not connected</Text>
                <Text style={styles.alpacaMeta}>
                  Link API keys in Settings to sync broker positions and place orders from this screen.
                </Text>
                <Pressable style={styles.alpacaBtn} onPress={() => router.push("/settings/integrations")}>
                  <Text style={styles.alpacaBtnTxt}>Open integrations</Text>
                </Pressable>
              </>
            )}
          </View>
          ) : null}

          <Text style={styles.allocTitle}>{activeView === "overview" ? "Asset allocation" : "Holdings allocation"}</Text>
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
              <Text style={styles.holdingsSub}>Quotes, Alpaca orders, manual lots</Text>
            </View>
            <Pressable style={styles.addHoldingBtn} onPress={() => setAddOpen(true)}>
              <MaterialCommunityIcons name="plus" size={22} color={theme.colors.onPrimary} />
              <Text style={styles.addHoldingBtnTxt}>Add</Text>
            </Pressable>
          </View>

          {positionsSorted.length === 0 ? (
            <Text style={styles.legendMuted}>No holdings yet.</Text>
          ) : (
            positionsSorted.map((p) => {
              const pl = p.plPct;
              const up = pl === null || pl >= 0;
              const isAlpaca = p.source === "alpaca";
              const qtyDisp = p.qty != null && Number.isFinite(p.qty) ? p.qty : null;
              return (
                <Pressable key={p.key} style={styles.holdingCard} onPress={() => setSelectedHolding(p)}>
                  <View style={styles.holdingTop}>
                    <View style={styles.holdingLeft}>
                      <View style={[styles.holdingIcon, { backgroundColor: p.accent.tile }]}>
                        <MaterialCommunityIcons name="domain" size={22} color={p.accent.ink} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <Text style={styles.holdingName} numberOfLines={1}>
                            {p.symbol}
                          </Text>
                          {isAlpaca ? (
                            <View style={styles.alpacaBadge}>
                              <Text style={styles.alpacaBadgeTxt}>Alpaca</Text>
                            </View>
                          ) : null}
                          {pl !== null ? (
                            <View style={[styles.plChip, { backgroundColor: up ? "rgba(22,163,74,0.12)" : "rgba(220,38,38,0.12)" }]}>
                              <Text style={[styles.plChipTxt, { color: up ? "#16a34a" : theme.colors.error }]}>
                                {up ? "+" : ""}{pl.toFixed(1)}%
                              </Text>
                            </View>
                          ) : null}
                        </View>
                        <Text style={styles.holdingMeta}>
                          {qtyDisp != null ? `${qtyDisp} sh · ` : ""}
                          {p.allocPct.toFixed(1)}% of portfolio
                        </Text>
                      </View>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={styles.holdingMv}>{fmtMoney(p.mv)}</Text>
                      <Text style={styles.allocFooter} numberOfLines={1}>Tap for detail</Text>
                    </View>
                  </View>
                  {isAlpaca && alpacaStatus?.connected && qtyDisp != null && qtyDisp > 0 ? (
                    <View style={styles.holdingFooterRow}>
                      <Text style={styles.allocFooter}>{p.allocPct.toFixed(1)}% allocation</Text>
                      <Pressable
                        style={styles.sellBtn}
                        onPress={(e) => { e.stopPropagation?.(); onSellAlpaca(p.symbol, qtyDisp); }}
                        hitSlop={8}
                      >
                        <Text style={styles.sellBtnTxt}>Market sell</Text>
                      </Pressable>
                    </View>
                  ) : null}
                </Pressable>
              );
            })
          )}

          {activeView === "overview" ? (
          <View style={styles.insightHeadRow}>
            <Text style={styles.insightSectionTitle}>Institutional Insights</Text>
            <Pressable onPress={() => router.push("/recommendations")}>
              <Text style={styles.recLink}>View Recommendations</Text>
            </Pressable>
          </View>
          ) : null}
          {activeView === "overview" ? (
          <View style={styles.insightCard}>
            <MaterialCommunityIcons name="lightbulb-on-outline" size={28} color={theme.colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.insightCardTitle}>{insightTitle}</Text>
              <Text style={styles.insightCardBody}>{insightBody}</Text>
            </View>
          </View>
          ) : null}
        </View>
      </ScrollView>

      <Modal visible={addOpen} transparent animationType="slide">
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Add position</Text>
            <Text style={styles.modalHint}>Creates a manual holding. If Alpaca is connected, you can place a market buy next.</Text>
            <Text style={styles.inputLabel}>Symbol</Text>
            <Input
              value={addSymbol}
              onChangeText={setAddSymbol}
              placeholder="AAPL"
              autoCapitalize="characters"
            />
            <Text style={styles.inputLabel}>Quantity</Text>
            <Input value={addQty} onChangeText={setAddQty} keyboardType="decimal-pad" placeholder="10" />
            <Text style={styles.inputLabel}>Average cost (USD)</Text>
            <Input value={addCost} onChangeText={setAddCost} keyboardType="decimal-pad" placeholder="150.00" />
            <View style={styles.modalActions}>
              <View style={{ flex: 1 }}>
                <Button title="Cancel" tone="secondary" onPress={() => setAddOpen(false)} disabled={addBusy} />
              </View>
              <View style={{ flex: 1 }}>
                <Button title="Save" onPress={submitAddHolding} loading={addBusy} disabled={addBusy} />
              </View>
            </View>
          </View>
        </View>
      </Modal>

      {/* Holding detail bottom sheet */}
      <Modal visible={selectedHolding !== null} transparent animationType="slide" onRequestClose={() => setSelectedHolding(null)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setSelectedHolding(null)}>
          <Pressable style={[styles.modalCard, { paddingBottom: insets.bottom + 16 }]} onPress={() => {}}>
            {selectedHolding ? (() => {
              const h = selectedHolding;
              const up = h.plPct === null || h.plPct >= 0;
              const plColor = up ? "#16a34a" : theme.colors.error;
              return (
                <>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 16 }}>
                    <View style={[styles.holdingIcon, { backgroundColor: h.accent.tile }]}>
                      <MaterialCommunityIcons name="domain" size={24} color={h.accent.ink} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.modalTitle, { marginBottom: 0 }]}>{h.symbol}</Text>
                      <Text style={styles.alpacaMeta}>{h.source === "alpaca" ? "Alpaca-linked" : "Manual"} · USD</Text>
                    </View>
                    <Pressable onPress={() => setSelectedHolding(null)} hitSlop={10}>
                      <MaterialCommunityIcons name="close" size={22} color={theme.colors.onSurfaceVariant} />
                    </Pressable>
                  </View>

                  <View style={{ gap: 10, marginBottom: 16 }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Text style={styles.alpacaMeta}>Market value</Text>
                      <Text style={styles.holdingMv}>{fmtMoney(h.mv)}</Text>
                    </View>
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Text style={styles.alpacaMeta}>Quantity</Text>
                      <Text style={[styles.holdingMeta, { fontFamily: "Inter_600SemiBold" }]}>{h.qty != null ? String(h.qty) : "—"} shares</Text>
                    </View>
                    {h.plPct !== null ? (
                      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                        <Text style={styles.alpacaMeta}>Unrealized P&L</Text>
                        <Text style={[styles.holdingMeta, { color: plColor, fontFamily: "Inter_700Bold" }]}>
                          {up ? "+" : ""}{h.plPct.toFixed(2)}%
                        </Text>
                      </View>
                    ) : null}
                    <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Text style={styles.alpacaMeta}>Portfolio weight</Text>
                      <Text style={[styles.holdingMeta, { fontFamily: "Inter_600SemiBold" }]}>{h.allocPct.toFixed(1)}%</Text>
                    </View>
                  </View>

                  {/* P&L mini bar */}
                  {h.plPct !== null ? (
                    <View style={{ marginBottom: 16 }}>
                      <View style={{ height: 8, borderRadius: 99, backgroundColor: theme.colors.surfaceContainerHigh, overflow: "hidden" }}>
                        <View style={{ width: `${Math.min(100, Math.abs(h.plPct))}%`, height: "100%", borderRadius: 99, backgroundColor: plColor }} />
                      </View>
                      <Text style={[styles.alpacaMeta, { marginTop: 4, textAlign: "right" }]}>
                        {up ? "Gain" : "Loss"} {Math.abs(h.plPct).toFixed(1)}% vs cost basis
                      </Text>
                    </View>
                  ) : null}

                  {h.source === "alpaca" && alpacaStatus?.connected && h.qty != null && h.qty > 0 ? (
                    <Pressable style={styles.sellBtn} onPress={() => { setSelectedHolding(null); onSellAlpaca(h.symbol, h.qty!); }}>
                      <Text style={styles.sellBtnTxt}>Market sell on Alpaca</Text>
                    </Pressable>
                  ) : null}
                </>
              );
            })() : null}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  scrollContent: { flexGrow: 1 },
  viewSwitchRow: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 8,
    marginBottom: 10,
    padding: 4,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    flexDirection: "row",
    gap: 6,
    ...theme.shadows.sm,
  },
  viewSwitchBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 999,
    alignItems: "center",
  },
  viewSwitchBtnOn: {
    backgroundColor: theme.colors.primary,
  },
  viewSwitchTxt: {
    fontSize: 12,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 0.7,
    textTransform: "uppercase",
  },
  viewSwitchTxtOn: {
    color: theme.colors.onPrimary,
  },
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
  rangeRow: { flexDirection: "row", gap: 6, marginTop: 12, paddingVertical: 2 },
  rangeChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.12)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.2)",
  },
  rangeChipOn: {
    backgroundColor: "#ffffff",
    borderColor: "#ffffff",
  },
  rangeTxt: { fontSize: 12, fontFamily: "Inter_700Bold", color: "rgba(255,255,255,0.8)", letterSpacing: 0.3 },
  rangeTxtOn: { color: theme.colors.primary, fontFamily: "Inter_800ExtraBold" },
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
    backgroundColor: theme.colors.background,
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
    ...theme.shadows.sm,
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
    ...theme.shadows.sm,
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
    fontSize: 10,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.secondary,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  holdingFooterRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 14,
    gap: 12,
  },
  sellBtn: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.errorContainer,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  sellBtnTxt: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: theme.colors.onErrorContainer },
  alpacaBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    backgroundColor: theme.colors.primaryContainer,
  },
  alpacaBadgeTxt: { fontSize: 10, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  addHoldingBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: theme.colors.primary,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: theme.radii.lg,
  },
  addHoldingBtnTxt: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimary },
  gainsNote: {
    marginTop: 8,
    fontSize: 11,
    color: "rgba(255,255,255,0.7)",
    fontFamily: "Inter_400Regular",
    lineHeight: 16,
  },
  alpacaSectionK: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    marginBottom: 10,
  },
  alpacaCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    padding: theme.spacing.lg,
    marginBottom: 20,
    gap: 12,
    ...theme.shadows.sm,
  },
  alpacaRow: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  alpacaTitle: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  alpacaMeta: { marginTop: 4, fontSize: 13, color: theme.colors.secondary, lineHeight: 18 },
  alpacaActions: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  alpacaBtn: {
    backgroundColor: theme.colors.primary,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: theme.radii.md,
  },
  alpacaBtnTxt: { fontSize: 14, fontFamily: "Inter_800ExtraBold", color: theme.colors.onPrimary },
  alpacaBtnSecondary: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  alpacaBtnSecondaryTxt: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.primary },
  alpacaHint: { fontSize: 12, color: theme.colors.secondary, lineHeight: 18 },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "center",
    padding: 24,
  },
  modalCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: 20,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.md,
  },
  modalTitle: { fontSize: 18, fontFamily: "Inter_800ExtraBold", marginBottom: 8, color: theme.colors.onSurface },
  modalHint: { fontSize: 12, color: theme.colors.secondary, marginBottom: 14, lineHeight: 18 },
  inputLabel: {
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    marginBottom: 6,
    marginTop: 10,
  },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 20 },
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
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.xl,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    marginBottom: 32,
    ...theme.shadows.sm,
  },
  insightCardTitle: {
    fontSize: 16,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
  },
  insightCardBody: {
    marginTop: 6,
    fontSize: 13,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    opacity: 0.9,
  },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", padding: 20 },
  plChip: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 6,
  },
  plChipTxt: {
    fontSize: 11,
    fontFamily: "Inter_700Bold",
  },
});
