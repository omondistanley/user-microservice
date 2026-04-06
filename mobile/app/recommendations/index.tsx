import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { gatewayJsonOptional } from "../../src/gatewayRequest";
import { useAppTheme, type AppTheme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";
import { ExpandableCard } from "../../src/components/ui/ExpandableCard";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";

type RecommendationItem = {
  symbol?: string;
  score?: string;
  confidence?: string;
  full_name?: string;
  sector?: string;
  why_shown_one_line?: string;
  bull_case?: string;
  bear_case?: string;
  data_badges?: unknown[];
};

type ExplainDetail = {
  analystNote?: string;
  whySelected?: string[];
  shap?: Record<string, number>;
  modelVersion?: string;
};

type LatestResponse = {
  run?: { run_id?: string; id?: string; created_at?: string };
  items?: RecommendationItem[];
  portfolio?: Record<string, unknown>;
  ui_insights?: Record<string, unknown>;
  page_state?: string;
  pagination?: { page: number; page_size: number; total_items: number; total_pages: number };
};

type RiskProfile = {
  risk_tolerance?: string;
  industry_preferences?: string[];
  sharpe_objective?: number | null;
  loss_aversion?: string;
  use_finance_data_for_recommendations?: boolean;
};

const RISK_CHIPS = ["conservative", "balanced", "aggressive"] as const;
const LOSS_CHIPS = ["low", "moderate", "high"] as const;

export default function RecommendationsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const theme = useAppTheme();
  const styles = useMemo(() => createStyles(theme), [theme]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<LatestResponse | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [risk, setRisk] = useState<RiskProfile | null>(null);
  const [riskLoading, setRiskLoading] = useState(true);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [editTolerance, setEditTolerance] = useState("balanced");
  const [editIndustries, setEditIndustries] = useState("");
  const [editSharpe, setEditSharpe] = useState("");
  const [editLoss, setEditLoss] = useState("moderate");
  const [editFinanceData, setEditFinanceData] = useState(false);
  const [expandedSym, setExpandedSym] = useState<string | null>(null);
  const [explainBySym, setExplainBySym] = useState<Record<string, ExplainDetail>>({});
  const [explainBusy, setExplainBusy] = useState<string | null>(null);
  const [holdingModal, setHoldingModal] = useState<{ symbol: string } | null>(null);
  const [hqty, setHqty] = useState("1");
  const [hcost, setHcost] = useState("");
  const [holdingBusy, setHoldingBusy] = useState(false);
  const [riskLoadError, setRiskLoadError] = useState<string | null>(null);
  const [dismissedSyms, setDismissedSyms] = useState<Set<string>>(new Set());
  const [reminderSyms, setReminderSyms] = useState<Set<string>>(new Set());
  const [surplusData, setSurplusData] = useState<Record<string, unknown> | null>(null);
  const [sectorData, setSectorData] = useState<{
    sectors?: { name: string; pct: number; value: number }[];
    concentration_warning?: boolean;
    total_value?: number;
  } | null>(null);
  const [digestData, setDigestData] = useState<{
    digest?: { headline?: string; body_text?: string; portfolio_score?: number; surplus_amount?: number } | null;
  } | null>(null);
  const [extrasLoading, setExtrasLoading] = useState(true);

  const runId = useMemo(() => {
    const r = resp?.run;
    if (!r) return "";
    return String((r as { run_id?: string }).run_id ?? (r as { id?: string }).id ?? "");
  }, [resp]);

  const loadRisk = useCallback(async () => {
    setRiskLoading(true);
    setRiskLoadError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/risk-profile`, {
        method: "GET",
      });
      const json = (await res.json().catch(() => null)) as RiskProfile | null;
      if (!res.ok) {
        setRisk(null);
        setRiskLoadError(formatApiDetail((json as any)?.detail, "Could not load risk profile."));
        return;
      }
      setRisk(json);
      setEditTolerance(String(json?.risk_tolerance ?? "balanced"));
      setEditIndustries((json?.industry_preferences ?? []).join(", "));
      setEditSharpe(json?.sharpe_objective != null ? String(json.sharpe_objective) : "");
      setEditLoss(String(json?.loss_aversion ?? "moderate"));
      setEditFinanceData(Boolean(json?.use_finance_data_for_recommendations));
    } catch {
      setRisk(null);
      setRiskLoadError("Could not load risk profile.");
    } finally {
      setRiskLoading(false);
    }
  }, []);

  const loadFinanceExtras = useCallback(async () => {
    setExtrasLoading(true);
    try {
      const [s, sec, dig] = await Promise.all([
        gatewayJsonOptional<Record<string, unknown>>("/api/v1/surplus", { method: "GET" }),
        gatewayJsonOptional<{
          sectors?: { name: string; pct: number; value: number }[];
          concentration_warning?: boolean;
          total_value?: number;
        }>("/api/v1/portfolio/sector-breakdown", { method: "GET" }),
        gatewayJsonOptional<{
          digest?: { headline?: string; body_text?: string; portfolio_score?: number; surplus_amount?: number } | null;
        }>("/api/v1/recommendations/digest/latest", { method: "GET" }),
      ]);
      setSurplusData(s.ok && s.data ? s.data : null);
      setSectorData(sec.ok && sec.data ? sec.data : null);
      setDigestData(dig.ok && dig.data ? dig.data : null);
    } finally {
      setExtrasLoading(false);
    }
  }, []);

  const fetchLatest = async (page = 1, append = false) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/recommendations/latest?page=${page}&page_size=20&enrich=1`,
        { method: "GET" },
      );
      const json = (await res.json().catch(() => null)) as LatestResponse | null;
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Failed to load recommendations."));
      }
      if (append && json) {
        setResp((prev) => {
          const prevItems = prev?.items ?? [];
          const nextItems = json.items ?? [];
          return { ...json, items: [...prevItems, ...nextItems] };
        });
      } else {
        setResp(json);
      }
      setCurrentPage(page);
      setTotalPages(Number(json?.pagination?.total_pages ?? 1) || 1);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load recommendations.");
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  };

  useEffect(() => {
    loadRisk();
  }, [loadRisk]);

  useEffect(() => {
    fetchLatest();
  }, []);

  useEffect(() => {
    loadFinanceExtras();
  }, [loadFinanceExtras]);

  const items: RecommendationItem[] = useMemo(() => resp?.items ?? [], [resp]);
  const pageState = String(resp?.page_state ?? "");

  const savePrefs = async () => {
    setSavingPrefs(true);
    setError(null);
    try {
      const sharpe =
        editSharpe.trim() === "" ? null : Number(editSharpe.replace(/,/g, ""));
      const body: Record<string, unknown> = {
        risk_tolerance: editTolerance,
        industry_preferences: editIndustries,
        loss_aversion: editLoss,
        use_finance_data_for_recommendations: editFinanceData,
      };
      if (sharpe !== null && Number.isFinite(sharpe)) body.sharpe_objective = sharpe;
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/risk-profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Failed to save preferences."));
      }
      setRisk(json as RiskProfile);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSavingPrefs(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/recommendations/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Run failed."));
      }
      await fetchLatest(1, false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Run failed.");
    } finally {
      setRunning(false);
    }
  };

  const loadExplain = async (symbol: string) => {
    if (!runId) {
      setError("No recommendation run id — run recommendations first.");
      return;
    }
    setExplainBusy(symbol);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/recommendations/${encodeURIComponent(runId)}/explain/${encodeURIComponent(symbol)}`,
        { method: "GET" },
      );
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Could not load details."));
      }
      const expl = (json as { explanation?: Record<string, unknown> })?.explanation ?? {};
      const sb = (expl.score_breakdown as Record<string, unknown> | undefined) ?? {};
      const fc = (expl.factor_contributions ?? sb.factor_contributions) as Record<string, number> | undefined;
      const shap: Record<string, number> | undefined =
        fc && typeof fc === "object"
          ? Object.fromEntries(
              Object.entries(fc).map(([k, v]) => [k, typeof v === "number" ? v : parseFloat(String(v)) || 0]),
            )
          : undefined;
      const whySelected = Array.isArray(expl.why_selected)
        ? (expl.why_selected as unknown[]).map(String).slice(0, 4)
        : undefined;
      const analystNote = String(expl.analyst_note_detail ?? expl.analyst_note ?? "").slice(0, 600) || undefined;
      const modelVersion = String(expl.model_version ?? sb.model_version ?? "").trim() || undefined;
      const detail: ExplainDetail = { analystNote, whySelected, shap, modelVersion };
      setExplainBySym((m) => ({ ...m, [symbol]: detail }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Explain failed.");
    } finally {
      setExplainBusy(null);
    }
  };

  const submitHolding = async () => {
    if (!holdingModal) return;
    const qty = Number(String(hqty).replace(/,/g, ""));
    const cost = Number(String(hcost).replace(/,/g, ""));
    if (!Number.isFinite(qty) || qty <= 0) {
      setError("Enter a valid quantity.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0) {
      setError("Enter a valid average cost.");
      return;
    }
    setHoldingBusy(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/holdings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: holdingModal.symbol.toUpperCase(),
          quantity: qty,
          avg_cost: cost,
          currency: "USD",
        }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Could not add holding."));
      }
      setHoldingModal(null);
      setHqty("1");
      setHcost("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Add holding failed.");
    } finally {
      setHoldingBusy(false);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={[
        styles.container,
        { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 32 },
      ]}
      keyboardShouldPersistTaps="handled"
    >
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Recommendations</Text>
        <View style={{ width: 60 }} />
      </View>

      {pageState === "volatile" ? (
        <View style={[styles.bannerCard, styles.bannerWarn]}>
          <Text style={styles.bannerTitle}>Markets are volatile</Text>
          <Text style={styles.bannerText}>Use this ranking as context only, not as an instruction to trade.</Text>
        </View>
      ) : null}
      {pageState === "first_run" ? (
        <View style={[styles.bannerCard, styles.bannerInfo]}>
          <Text style={styles.bannerTitle}>First run setup</Text>
          <Text style={styles.bannerText}>Save preferences, then run analysis to generate your first ranked set.</Text>
        </View>
      ) : null}
      {pageState === "steady" ? (
        <View style={[styles.bannerCard, styles.bannerOk]}>
          <Text style={styles.bannerTitle}>Portfolio looks steady</Text>
          <Text style={styles.bannerText}>Current allocation appears within expected range for your settings.</Text>
        </View>
      ) : null}

      <Text style={styles.sectionK}>Your preferences (used by the engine)</Text>
      {riskLoadError ? <Text style={styles.errorText}>{riskLoadError}</Text> : null}
      {riskLoading ? (
        <ActivityIndicator color={theme.colors.primary} />
      ) : (
        <View style={styles.prefsCard}>
          <Text style={styles.label}>Risk tolerance</Text>
          <View style={styles.chipRow}>
            {RISK_CHIPS.map((c) => {
              const on = editTolerance === c;
              return (
                <Pressable key={c} style={[styles.chip, on && styles.chipOn]} onPress={() => setEditTolerance(c)}>
                  <Text style={[styles.chipTxt, on && styles.chipTxtOn]}>{c}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={[styles.label, { marginTop: 12 }]}>Industries (comma-separated)</Text>
          <Input
            value={editIndustries}
            onChangeText={setEditIndustries}
            placeholder="technology, healthcare, broad_market"
          />
          <Text style={[styles.label, { marginTop: 12 }]}>Sharpe objective (optional)</Text>
          <Input value={editSharpe} onChangeText={setEditSharpe} keyboardType="decimal-pad" placeholder="e.g. 0.5" />
          <Text style={[styles.label, { marginTop: 12 }]}>Loss aversion</Text>
          <View style={styles.chipRow}>
            {LOSS_CHIPS.map((c) => {
              const on = editLoss === c;
              return (
                <Pressable key={c} style={[styles.chip, on && styles.chipOn]} onPress={() => setEditLoss(c)}>
                  <Text style={[styles.chipTxt, on && styles.chipTxtOn]}>{c}</Text>
                </Pressable>
              );
            })}
          </View>
          <View style={styles.switchRow}>
            <Text style={styles.switchLabel}>Use finance data (budgets, goals) in recommendations</Text>
            <Switch value={editFinanceData} onValueChange={setEditFinanceData} />
          </View>
          <Button title="Save preferences" onPress={savePrefs} loading={savingPrefs} disabled={savingPrefs} />
        </View>
      )}

      <View style={styles.actionsRow}>
        {running ? <ActivityIndicator color={theme.colors.primary} /> : <Button title="Run now" onPress={runNow} />}
      </View>

      <Text style={[styles.sectionK, { marginTop: 8 }]}>Context (web parity)</Text>
      {extrasLoading ? (
        <ActivityIndicator color={theme.colors.primary} style={{ alignSelf: "flex-start" }} />
      ) : (
        <View style={styles.prefsCard}>
          {digestData?.digest ? (
            <>
              <Text style={styles.label}>Latest digest</Text>
              <Text style={styles.blockBody}>
                {(digestData.digest.headline || "").trim() || "—"}
              </Text>
              {digestData.digest.body_text ? (
                <Text style={[styles.blockBody, { marginTop: 6 }]}>
                  {String(digestData.digest.body_text).slice(0, 500)}
                  {String(digestData.digest.body_text).length > 500 ? "…" : ""}
                </Text>
              ) : null}
            </>
          ) : (
            <Text style={styles.mutedText}>No weekly digest yet.</Text>
          )}
          {surplusData && typeof surplusData.investable_surplus === "number" ? (
            <>
              <Text style={[styles.label, { marginTop: 12 }]}>Investable surplus (estimate)</Text>
              <Text style={styles.blockBody}>
                ${Number(surplusData.investable_surplus).toFixed(2)} —{" "}
                {String(surplusData.disclaimer || "").slice(0, 120)}
              </Text>
            </>
          ) : (
            <Text style={[styles.mutedText, { marginTop: 10 }]}>Surplus data unavailable.</Text>
          )}
          {sectorData?.sectors?.length ? (
            <>
              <Text style={[styles.label, { marginTop: 12 }]}>Sector mix</Text>
              {sectorData.sectors.slice(0, 6).map((s) => (
                <Text key={s.name} style={styles.blockBody}>
                  {s.name}: {s.pct}% (${s.value.toFixed(0)})
                </Text>
              ))}
              {sectorData.concentration_warning ? (
                <Text style={[styles.blockBody, { color: "#b45309", marginTop: 6 }]}>
                  Concentration warning: one sector exceeds threshold.
                </Text>
              ) : null}
            </>
          ) : (
            <Text style={[styles.mutedText, { marginTop: 10 }]}>No holdings for sector breakdown.</Text>
          )}
        </View>
      )}

      <Text style={styles.sectionK}>Portfolio risk snapshot</Text>
      <View style={styles.prefsCard}>
        {resp?.portfolio ? (
          <>
            <Text style={styles.blockBody}>Total value: ${Number((resp.portfolio as any).total_value ?? 0).toFixed(2)}</Text>
            <Text style={styles.blockBody}>Sharpe: {String((resp.portfolio as any).sharpe ?? "—")}</Text>
            <Text style={styles.blockBody}>Volatility (annual): {String((resp.portfolio as any).volatility_annual ?? "—")}</Text>
            <Text style={styles.blockBody}>Max drawdown: {String((resp.portfolio as any).max_drawdown ?? "—")}</Text>
          </>
        ) : (
          <Text style={styles.mutedText}>Run recommendations to see portfolio risk metrics.</Text>
        )}
      </View>

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      {loading ? (
        <ActivityIndicator style={{ marginTop: 16 }} color={theme.colors.primary} />
      ) : items.length ? (
        items.filter((it) => !dismissedSyms.has(String(it.symbol ?? "").trim().toUpperCase())).map((it, idx) => {
          const sym = String(it.symbol ?? "").trim().toUpperCase();
          const open = expandedSym === sym;
          const toggleSym = () => {
            if (!sym) return;
            setExpandedSym(open ? null : sym);
          };
          return (
            <ExpandableCard
              key={`${sym || "x"}-${idx}`}
              expanded={open}
              onToggle={toggleSym}
              onSummaryPress={toggleSym}
              style={styles.cardOuter}
              summary={
                <View style={styles.rowInner}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{it.symbol ?? "—"}</Text>
                    {it.full_name ? <Text style={styles.fullName}>{it.full_name}</Text> : null}
                    <Text style={styles.subText}>{it.why_shown_one_line ?? ""}</Text>
                    {it.sector ? <Text style={styles.metaText}>Sector: {it.sector}</Text> : null}
                  </View>
                  <View style={{ alignItems: "flex-end", minWidth: 72 }}>
                    <Text style={styles.scoreText}>Score: {it.score ?? "—"}</Text>
                    {(() => {
                      const raw = it.confidence != null ? parseFloat(String(it.confidence)) : null;
                      const pct = raw != null && !isNaN(raw) ? (raw <= 1 ? Math.round(raw * 100) : Math.round(raw)) : null;
                      const barColor = pct == null ? "#94a3b8" : pct >= 75 ? "#10b981" : pct >= 50 ? "#f59e0b" : "#ef4444";
                      return pct != null ? (
                        <View style={{ width: 72, marginTop: 6 }}>
                          <Text style={[styles.confText, { color: barColor }]}>{pct}% conf</Text>
                          <View style={{ height: 4, borderRadius: 99, backgroundColor: "rgba(0,0,0,0.08)", marginTop: 3, overflow: "hidden" }}>
                            <View style={{ width: `${pct}%` as any, height: "100%", borderRadius: 99, backgroundColor: barColor }} />
                          </View>
                        </View>
                      ) : <Text style={styles.confText}>Conf: —</Text>;
                    })()}
                  </View>
                </View>
              }
            >
              {sym ? (
                <>
                  {it.bull_case ? (
                    <Text style={styles.blockLabel}>Bull case</Text>
                  ) : null}
                  {it.bull_case ? <Text style={styles.blockBody}>{it.bull_case}</Text> : null}
                  {it.bear_case ? <Text style={styles.blockLabel}>Bear case</Text> : null}
                  {it.bear_case ? <Text style={styles.blockBody}>{it.bear_case}</Text> : null}
                  <Button
                    title={explainBySym[sym] ? "Refresh detail" : "Load analyst detail"}
                    onPress={() => loadExplain(sym)}
                    loading={explainBusy === sym}
                    disabled={explainBusy !== null}
                    tone="secondary"
                  />
                  {explainBySym[sym] ? (() => {
                    const d = explainBySym[sym];
                    const shapEntries = d.shap
                      ? Object.entries(d.shap)
                          .filter(([, v]) => Math.abs(v) > 0.0001)
                          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                      : [];
                    const maxAbs = shapEntries.length
                      ? Math.max(...shapEntries.map(([, v]) => Math.abs(v)))
                      : 1;
                    const SHAP_LABELS: Record<string, string> = {
                      heuristic_score: "Risk-adj. score",
                      weight: "Position weight",
                      vol_annual: "Volatility",
                      hhi: "Concentration",
                      tlh_loss_scaled: "TLH opportunity",
                    };
                    return (
                      <View style={styles.explainSection}>
                        {shapEntries.length > 0 && (
                          <View style={styles.shapBlock}>
                            <Text style={styles.shapTitle}>Score drivers</Text>
                            {shapEntries.map(([key, val]) => {
                              const barPct = (Math.abs(val) / maxAbs) * 100;
                              const barColor = val > 0 ? theme.colors.primary : "#e53e3e";
                              const label = SHAP_LABELS[key] ?? key.replace(/_/g, " ");
                              return (
                                <View key={key} style={styles.shapRow}>
                                  <Text style={styles.shapLabel}>{label}</Text>
                                  <View style={styles.shapTrack}>
                                    <View style={[styles.shapFill, { width: `${barPct}%` as any, backgroundColor: barColor }]} />
                                  </View>
                                  <Text style={[styles.shapVal, { color: val > 0 ? theme.colors.primary : "#e53e3e" }]}>
                                    {(val > 0 ? "+" : "") + val.toFixed(3)}
                                  </Text>
                                </View>
                              );
                            })}
                            {d.modelVersion ? (
                              <Text style={styles.shapMeta}>Model: {d.modelVersion}</Text>
                            ) : null}
                          </View>
                        )}
                        {d.whySelected && d.whySelected.length > 0 && (
                          <View style={{ marginTop: 8 }}>
                            <Text style={styles.shapTitle}>Why selected</Text>
                            {d.whySelected.map((line, i) => (
                              <Text key={i} style={styles.explainLine}>· {line}</Text>
                            ))}
                          </View>
                        )}
                        {d.analystNote ? (
                          <View style={{ marginTop: 8 }}>
                            <Text style={styles.shapTitle}>Analyst note</Text>
                            <Text style={styles.explainBox}>{d.analystNote}</Text>
                          </View>
                        ) : null}
                      </View>
                    );
                  })() : null}
                  <View style={[styles.rowGap, { flexDirection: "row", gap: 8 }]}>
                    <Pressable
                      style={[styles.actionBtn, { backgroundColor: theme.colors.primaryContainer, flex: 1 }]}
                      onPress={() => setHoldingModal({ symbol: sym })}
                    >
                      <Text style={[styles.actionBtnTxt, { color: theme.colors.onPrimaryContainer }]}>Do this</Text>
                    </Pressable>
                    <Pressable
                      style={[styles.actionBtn, { backgroundColor: reminderSyms.has(sym) ? theme.colors.secondaryContainer : theme.colors.surfaceContainerHigh, flex: 1 }]}
                      onPress={() => setReminderSyms((prev) => { const n = new Set(prev); n.has(sym) ? n.delete(sym) : n.add(sym); return n; })}
                    >
                      <Text style={[styles.actionBtnTxt, { color: reminderSyms.has(sym) ? theme.colors.onSecondaryContainer : theme.colors.onSurfaceVariant }]}>
                        {reminderSyms.has(sym) ? "Reminded ✓" : "Remind me"}
                      </Text>
                    </Pressable>
                    <Pressable
                      style={[styles.actionBtn, { backgroundColor: theme.colors.errorContainer, flex: 1 }]}
                      onPress={() => { setDismissedSyms((prev) => { const n = new Set(prev); n.add(sym); return n; }); setExpandedSym(null); }}
                    >
                      <Text style={[styles.actionBtnTxt, { color: theme.colors.onErrorContainer }]}>Not for me</Text>
                    </Pressable>
                  </View>
                </>
              ) : null}
            </ExpandableCard>
          );
        })
      ) : (
        <Text style={styles.mutedText}>No recommendations yet. Save preferences and tap Run now.</Text>
      )}

      {currentPage < totalPages ? (
        <Button
          title={loadingMore ? "Loading..." : `Load more (${currentPage}/${totalPages})`}
          onPress={() => fetchLatest(currentPage + 1, true)}
          loading={loadingMore}
          disabled={loadingMore}
          tone="secondary"
        />
      ) : null}

      <Modal visible={holdingModal !== null} transparent animationType="slide">
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Add {holdingModal?.symbol}</Text>
            <Text style={styles.label}>Quantity</Text>
            <Input value={hqty} onChangeText={setHqty} keyboardType="decimal-pad" />
            <Text style={[styles.label, { marginTop: 10 }]}>Average cost (USD)</Text>
            <Input value={hcost} onChangeText={setHcost} keyboardType="decimal-pad" placeholder="0.00" />
            <View style={styles.modalActions}>
              <View style={{ flex: 1 }}>
                <Button title="Cancel" tone="secondary" onPress={() => setHoldingModal(null)} disabled={holdingBusy} />
              </View>
              <View style={{ flex: 1 }}>
                <Button title="Save" onPress={submitHolding} loading={holdingBusy} disabled={holdingBusy} />
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  container: { flexGrow: 1, paddingHorizontal: 20, backgroundColor: theme.colors.background, gap: 14 },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backBtn: { width: 60 },
  backText: { color: theme.colors.primary, fontFamily: "Inter_800ExtraBold" },
  title: { fontSize: 22, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  sectionK: {
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  prefsCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    padding: 14,
    gap: 8,
    ...theme.shadows.sm,
  },
  label: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurfaceVariant },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.surface,
  },
  chipOn: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
  chipTxt: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  chipTxtOn: { color: theme.colors.onPrimary },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginVertical: 8 },
  switchLabel: { flex: 1, fontSize: 13, fontFamily: "Inter_500Medium", color: theme.colors.onSurface, marginRight: 12 },
  actionsRow: { marginTop: 4 },
  bannerCard: {
    borderRadius: theme.radii.md,
    borderWidth: 1,
    padding: 12,
    ...theme.shadows.sm,
  },
  bannerInfo: { backgroundColor: theme.colors.primaryContainer, borderColor: theme.colors.primary },
  bannerWarn: { backgroundColor: theme.colors.tertiaryContainer, borderColor: theme.colors.tertiary },
  bannerOk: { backgroundColor: theme.colors.secondaryContainer, borderColor: theme.colors.secondary },
  bannerTitle: { fontSize: 13, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  bannerText: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginTop: 4 },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
  cardOuter: { marginBottom: 6 },
  rowInner: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  rowTitle: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  fullName: { fontSize: 13, color: theme.colors.onSurfaceVariant, marginTop: 3 },
  subText: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginTop: 6 },
  metaText: { fontSize: 12, color: theme.colors.secondary, marginTop: 6 },
  scoreText: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  confText: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary, marginTop: 4 },
  mutedText: { color: theme.colors.secondary, fontFamily: "Inter_400Regular" },
  blockLabel: { fontSize: 11, fontFamily: "Inter_800ExtraBold", color: theme.colors.primary, marginTop: 4 },
  blockBody: { fontSize: 12, color: theme.colors.onSurface, lineHeight: 18 },
  explainBox: {
    fontSize: 10,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurfaceVariant,
    backgroundColor: theme.colors.surfaceContainerLow,
    padding: 10,
    borderRadius: theme.radii.md,
    maxHeight: 220,
  },
  rowGap: { marginTop: 8 },
  explainSection: { marginTop: 8, gap: 0 },
  shapBlock: { marginBottom: 8 },
  shapTitle: { fontSize: 10, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurfaceVariant, textTransform: "uppercase", letterSpacing: 0.6, marginBottom: 6 },
  shapRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 5 },
  shapLabel: { width: 110, fontSize: 11, color: theme.colors.onSurfaceVariant },
  shapTrack: { flex: 1, height: 6, backgroundColor: theme.colors.outlineVariant, borderRadius: 99, overflow: "hidden" },
  shapFill: { height: "100%", borderRadius: 99 },
  shapVal: { width: 46, fontSize: 11, textAlign: "right", fontVariant: ["tabular-nums"] },
  shapMeta: { fontSize: 10, color: theme.colors.onSurfaceVariant, marginTop: 4, opacity: 0.7 },
  explainLine: { fontSize: 12, color: theme.colors.onSurface, lineHeight: 17, marginBottom: 3 },
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
  modalTitle: { fontSize: 18, fontFamily: "Inter_800ExtraBold", marginBottom: 12, color: theme.colors.onSurface },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 16 },
  actionBtn: {
    paddingVertical: 9,
    paddingHorizontal: 10,
    borderRadius: 8,
    alignItems: "center" as const,
    justifyContent: "center" as const,
  },
  actionBtnTxt: {
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    textAlign: "center" as const,
  },
});
