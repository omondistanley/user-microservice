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
import { theme } from "../../src/theme";
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
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resp, setResp] = useState<LatestResponse | null>(null);
  const [risk, setRisk] = useState<RiskProfile | null>(null);
  const [riskLoading, setRiskLoading] = useState(true);
  const [savingPrefs, setSavingPrefs] = useState(false);
  const [editTolerance, setEditTolerance] = useState("balanced");
  const [editIndustries, setEditIndustries] = useState("");
  const [editSharpe, setEditSharpe] = useState("");
  const [editLoss, setEditLoss] = useState("moderate");
  const [editFinanceData, setEditFinanceData] = useState(false);
  const [expandedSym, setExpandedSym] = useState<string | null>(null);
  const [explainBySym, setExplainBySym] = useState<Record<string, string>>({});
  const [explainBusy, setExplainBusy] = useState<string | null>(null);
  const [holdingModal, setHoldingModal] = useState<{ symbol: string } | null>(null);
  const [hqty, setHqty] = useState("1");
  const [hcost, setHcost] = useState("");
  const [holdingBusy, setHoldingBusy] = useState(false);
  const [riskLoadError, setRiskLoadError] = useState<string | null>(null);
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

  const fetchLatest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/recommendations/latest?page=1&page_size=50&enrich=1`,
        { method: "GET" },
      );
      const json = (await res.json().catch(() => null)) as LatestResponse | null;
      if (!res.ok) {
        throw new Error(formatApiDetail((json as any)?.detail, "Failed to load recommendations."));
      }
      setResp(json);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load recommendations.");
    } finally {
      setLoading(false);
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
      await fetchLatest();
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
      const expl = (json as { explanation?: unknown })?.explanation;
      const text =
        typeof expl === "object" && expl !== null
          ? JSON.stringify(expl, null, 2).slice(0, 4000)
          : String(expl ?? "");
      setExplainBySym((m) => ({ ...m, [symbol]: text }));
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

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      {loading ? (
        <ActivityIndicator style={{ marginTop: 16 }} color={theme.colors.primary} />
      ) : items.length ? (
        items.map((it, idx) => {
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
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.scoreText}>Score: {it.score ?? "—"}</Text>
                    <Text style={styles.confText}>Conf: {it.confidence ?? "—"}</Text>
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
                    title={explainBySym[sym] ? "Refresh analyst detail" : "Load analyst detail"}
                    onPress={() => loadExplain(sym)}
                    loading={explainBusy === sym}
                    disabled={explainBusy !== null}
                    tone="secondary"
                  />
                  {explainBySym[sym] ? <Text style={styles.explainBox}>{explainBySym[sym]}</Text> : null}
                  <View style={styles.rowGap}>
                    <Button title="Add to holdings…" onPress={() => setHoldingModal({ symbol: sym })} tone="secondary" />
                  </View>
                </>
              ) : null}
            </ExpandableCard>
          );
        })
      ) : (
        <Text style={styles.mutedText}>No recommendations yet. Save preferences and tap Run now.</Text>
      )}

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

const styles = StyleSheet.create({
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
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
  cardOuter: { marginBottom: 4 },
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
  },
  modalTitle: { fontSize: 18, fontFamily: "Inter_800ExtraBold", marginBottom: 12, color: theme.colors.onSurface },
  modalActions: { flexDirection: "row", gap: 10, marginTop: 16 },
});
