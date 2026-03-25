import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

const CATEGORY_NAMES: Record<number, string> = {
  1: "Food",
  2: "Transportation",
  3: "Travel",
  4: "Utilities",
  5: "Entertainment",
  6: "Health",
  7: "Shopping",
  8: "Other",
};

type SummaryItem = {
  group_key?: string;
  label?: string;
  total_amount?: string | number;
  count?: number;
};

type SummaryResponse = {
  group_by?: string;
  items?: SummaryItem[];
};

type SettingsResponse = {
  default_currency?: string;
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

function fmtSignedPct(pct: number | null): string {
  if (pct === null) return "—";
  const rounded = Math.round(pct * 10) / 10;
  const sign = rounded >= 0 ? "+" : "";
  return `${sign}${rounded.toFixed(1)}%`;
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function getDateRange(range: "month" | "quarter" | "year"): { dateFrom: string; dateTo: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const to = isoDate(now);
  let from: Date;
  if (range === "month") {
    from = new Date(y, m, 1);
  } else if (range === "quarter") {
    const qStart = Math.floor(m / 3) * 3;
    from = new Date(y, qStart, 1);
  } else {
    from = new Date(y, 0, 1);
  }
  return { dateFrom: isoDate(from), dateTo: to };
}

function getPrevDateRange(range: "month" | "quarter" | "year"): { dateFrom: string; dateTo: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  if (range === "month") {
    const to = new Date(y, m, 0);
    const from = new Date(y, m - 1, 1);
    return { dateFrom: isoDate(from), dateTo: isoDate(to) };
  }
  if (range === "quarter") {
    const qStart = Math.floor(m / 3) * 3;
    const to = new Date(y, qStart, 0);
    const from = new Date(y, qStart - 3, 1);
    return { dateFrom: isoDate(from), dateTo: isoDate(to) };
  }
  // year
  const to = new Date(y - 1, 11, 31);
  const from = new Date(y - 1, 0, 1);
  return { dateFrom: isoDate(from), dateTo: isoDate(to) };
}

const CURRENCIES = ["USD", "EUR", "GBP"] as const;
type Currency = (typeof CURRENCIES)[number];

function rangeLabel(range: "month" | "quarter" | "year"): string {
  return range === "month" ? "This Month" : range === "quarter" ? "This Quarter" : "This Year";
}
function prevRangeLabel(range: "month" | "quarter" | "year"): string {
  return range === "month" ? "Last Month" : range === "quarter" ? "Last Quarter" : "Last Year";
}

export default function ReportsScreen() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [range, setRange] = useState<"month" | "quarter" | "year">("month");
  const [currency, setCurrency] = useState<Currency>("USD");

  const [categoryItems, setCategoryItems] = useState<SummaryItem[]>([]);
  const [prevCategoryItems, setPrevCategoryItems] = useState<SummaryItem[]>([]);
  const [monthItems, setMonthItems] = useState<SummaryItem[]>([]);

  const [saveName, setSaveName] = useState("");
  const [reportSearch, setReportSearch] = useState("");
  const [saving, setSaving] = useState(false);

  const dateRange = useMemo(() => getDateRange(range), [range]);
  const prevDateRange = useMemo(() => getPrevDateRange(range), [range]);

  const currentTotal = useMemo(() => {
    const sum = (categoryItems ?? []).reduce((acc, i) => {
      const n = toNumber(i.total_amount) ?? 0;
      return acc + Math.abs(n);
    }, 0);
    return sum;
  }, [categoryItems]);

  const prevTotal = useMemo(() => {
    const sum = (prevCategoryItems ?? []).reduce((acc, i) => {
      const n = toNumber(i.total_amount) ?? 0;
      return acc + Math.abs(n);
    }, 0);
    return sum;
  }, [prevCategoryItems]);

  const topCategory = useMemo(() => {
    const item = (categoryItems ?? [])[0];
    if (!item) return null;
    const code = toNumber(item.group_key);
    const label = item.label ?? (code ? CATEGORY_NAMES[code] : null) ?? "Other";
    return { label };
  }, [categoryItems]);

  const vsPreviousPct = useMemo(() => {
    if (!prevTotal) return null;
    return ((currentTotal - prevTotal) / prevTotal) * 100;
  }, [currentTotal, prevTotal]);

  const fetchCategorySummary = async (params: { dateFrom: string; dateTo: string }) => {
    const res = await authClient.requestWithRefresh(
      `${GATEWAY_BASE_URL}/api/v1/expenses/summary?group_by=category&date_from=${encodeURIComponent(params.dateFrom)}&date_to=${encodeURIComponent(
        params.dateTo,
      )}&convert_to=${encodeURIComponent(currency)}`,
      { method: "GET" },
    );
    const json = (await res.json().catch(() => null)) as SummaryResponse | null;
    if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to load report summary.");
    return Array.isArray(json?.items) ? (json!.items as SummaryItem[]) : [];
  };

  const fetchMonthSummary = async (params: { dateFrom: string; dateTo: string }) => {
    const res = await authClient.requestWithRefresh(
      `${GATEWAY_BASE_URL}/api/v1/expenses/summary?group_by=month&date_from=${encodeURIComponent(params.dateFrom)}&date_to=${encodeURIComponent(
        params.dateTo,
      )}&convert_to=${encodeURIComponent(currency)}`,
      { method: "GET" },
    );
    const json = (await res.json().catch(() => null)) as SummaryResponse | null;
    if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to load monthly trend.");
    return Array.isArray(json?.items) ? (json!.items as SummaryItem[]) : [];
  };

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const settingsRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/settings`, { method: "GET" });
      const settingsJson = (await settingsRes.json().catch(() => null)) as SettingsResponse | null;
      if (settingsRes.ok && settingsJson?.default_currency) {
        const c = String(settingsJson.default_currency).toUpperCase();
        if ((CURRENCIES as readonly string[]).includes(c)) setCurrency(c as Currency);
      }

      const [curCats, prevCats, months] = await Promise.all([
        fetchCategorySummary(dateRange),
        fetchCategorySummary(prevDateRange),
        fetchMonthSummary(dateRange),
      ]);

      setCategoryItems(curCats);
      setPrevCategoryItems(prevCats);
      setMonthItems(months);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load reports.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, currency]);

  const saveView = async () => {
    setSaving(true);
    try {
      const name = saveName.trim();
      if (!name) throw new Error("Please enter a name for this saved view.");

      const payload = {
        name,
        payload: { period: range, currency, date_from: dateRange.dateFrom, date_to: dateRange.dateTo },
      };

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/reports/saved-views`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to save view.");

      router.replace("/saved-views");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const categoryRows = useMemo(() => {
    const q = reportSearch.trim().toLowerCase();
    const rows = categoryItems ?? [];
    if (!q) return rows;
    return rows.filter((i) => {
      const code = toNumber(i.group_key);
      const label = (i.label ?? (code ? CATEGORY_NAMES[code] : null) ?? "Other").toLowerCase();
      return label.includes(q);
    });
  }, [categoryItems, reportSearch]);
  const monthRows = useMemo(() => monthItems ?? [], [monthItems]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Reports</Text>
        <View style={{ width: 60 }} />
      </View>

      <View style={styles.heroCard}>
        <Text style={styles.heroKicker}>Institutional report</Text>
        <Text style={styles.heroTitle}>Financial reports & analytics</Text>
        <Text style={styles.heroBody}>
          Build focused reports for spending, cashflow and trend analysis, then save reusable views.
        </Text>
      </View>

      <View style={styles.searchWrap}>
        <TextInput
          value={reportSearch}
          onChangeText={setReportSearch}
          style={styles.searchInput}
          placeholder="Search reports, audits or monthly summaries"
          placeholderTextColor="#94a3b8"
        />
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Recent reports</Text>
        <View style={styles.reportTile}>
          <Text style={styles.reportTileK}>Monthly recap</Text>
          <Text style={styles.reportTileTitle}>October 2023 Summary</Text>
          <Text style={styles.reportTileMeta}>
            Comprehensive analysis of your cash flow, savings rate, and category trends for the period.
          </Text>
        </View>
        <View style={styles.reportTileLight}>
          <Text style={styles.reportTileK}>Quarterly</Text>
          <Text style={styles.reportTileTitleLight}>Q3 Investment Performance</Text>
          <Text style={styles.reportTileMetaLight}>Detailed breakdown of portfolio returns and benchmark comparison.</Text>
        </View>
      </View>

      <View style={styles.pickerBlock}>
        <Text style={styles.sectionLabel}>Period</Text>
        <View style={styles.pickerRow}>
          {(["month", "quarter", "year"] as const).map((r) => (
            <Pressable key={r} onPress={() => setRange(r)} style={[styles.pill, range === r ? styles.pillActive : null]}>
              <Text style={[styles.pillText, range === r ? styles.pillTextActive : null]}>{rangeLabel(r)}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={styles.pickerBlock}>
        <Text style={styles.sectionLabel}>Currency</Text>
        <View style={styles.pickerRow}>
          {CURRENCIES.map((c) => (
            <Pressable key={c} onPress={() => setCurrency(c)} style={[styles.pill, currency === c ? styles.pillActive : null]}>
              <Text style={[styles.pillText, currency === c ? styles.pillTextActive : null]}>{c}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <>
          <View style={styles.statsGrid}>
            <View style={styles.statCard}>
              <Text style={styles.statLabel}>Total spent</Text>
              <Text style={styles.statValue}>{fmtMoney(currentTotal)}</Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statLabel}>vs previous</Text>
              <Text style={styles.statValue}>{fmtSignedPct(vsPreviousPct)}</Text>
              <Text style={styles.statMeta}>{prevRangeLabel(range)}</Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statLabel}>Top category</Text>
              <Text style={styles.statValue}>{topCategory?.label ?? "—"}</Text>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Spending by category</Text>
            {(categoryRows ?? []).slice(0, 12).map((i, idx) => {
              const total = Math.abs(toNumber(i.total_amount) ?? 0);
              const pct = currentTotal ? (total / currentTotal) * 100 : 0;
              const code = toNumber(i.group_key);
              const label = i.label ?? (code ? CATEGORY_NAMES[code] : null) ?? "Other";
              return (
                <View key={`${String(i.group_key ?? idx)}`} style={styles.categoryRow}>
                  <Text style={styles.catLabel} numberOfLines={1}>
                    {label}
                  </Text>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.catAmount}>{fmtMoney(total)}</Text>
                    <Text style={styles.catPct}>{Math.round(pct)}% share</Text>
                  </View>
                </View>
              );
            })}
            {(categoryRows ?? []).length === 0 ? <Text style={styles.mutedText}>No spending in this period.</Text> : null}
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Monthly trend</Text>
            {(monthRows ?? []).slice(0, 12).map((m, idx) => {
              const total = Math.abs(toNumber(m.total_amount) ?? 0);
              const label = m.label ?? m.group_key ?? `Month ${idx + 1}`;
              return (
                <View key={`${String(m.group_key ?? idx)}`} style={styles.monthRow}>
                  <Text style={styles.monthLabel}>{String(label)}</Text>
                  <Text style={styles.monthAmount}>{fmtMoney(total)}</Text>
                </View>
              );
            })}
            {(monthRows ?? []).length === 0 ? <Text style={styles.mutedText}>No trend data.</Text> : null}
          </View>

          <View style={styles.saveCard}>
            <Text style={styles.sectionTitle}>Save this view</Text>
            <TextInput
              value={saveName}
              onChangeText={setSaveName}
              style={styles.input}
              placeholder="View name"
              autoCapitalize="words"
            />
            <View style={{ marginTop: 10 }}>
              {saving ? (
                <ActivityIndicator />
              ) : (
                <Pressable style={styles.primaryBtn} onPress={saveView}>
                  <Text style={styles.primaryBtnText}>Save</Text>
                </Pressable>
              )}
            </View>
            <Text style={styles.mutedText}>Saved views are available in `Saved Views`.</Text>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 12, backgroundColor: "#fff" },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backBtn: { width: 60 },
  backText: { color: "#135bec", fontWeight: "900" },
  title: { fontSize: 24, fontWeight: "900" },
  heroCard: { backgroundColor: "#0f172a", borderRadius: 18, padding: 16, marginTop: 2 },
  heroKicker: { fontSize: 10, fontWeight: "900", color: "#93c5fd", letterSpacing: 1.5, textTransform: "uppercase" },
  heroTitle: { marginTop: 6, fontSize: 26, fontWeight: "900", color: "#fff" },
  heroBody: { marginTop: 6, fontSize: 13, color: "rgba(255,255,255,0.75)", lineHeight: 18, fontWeight: "600" },
  searchWrap: { marginTop: 8 },
  searchInput: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    backgroundColor: "#f8fafc",
    color: "#0f172a",
    fontWeight: "700",
  },
  pickerBlock: { gap: 8 },
  sectionLabel: { fontSize: 12, fontWeight: "900", color: "#64748b" },
  pickerRow: { flexDirection: "row", gap: 10, flexWrap: "wrap" },
  pill: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: "#fff" },
  pillActive: { borderColor: "#135bec", backgroundColor: "#dbeafe" },
  pillText: { fontWeight: "900", color: "#0f172a", fontSize: 13 },
  pillTextActive: { color: "#135bec" },
  errorText: { color: "#dc2626", fontWeight: "900" },
  statsGrid: { flexDirection: "row", gap: 12, flexWrap: "wrap" },
  statCard: { flex: 1, minWidth: 140, borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 14, backgroundColor: "#fff", gap: 4 },
  statLabel: { fontSize: 12, fontWeight: "900", color: "#64748b" },
  statValue: { fontSize: 18, fontWeight: "900", color: "#0f172a" },
  statMeta: { fontSize: 11, fontWeight: "900", color: "#64748b", marginTop: 2 },
  card: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, backgroundColor: "#fff", gap: 10 },
  sectionTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a" },
  reportTile: { backgroundColor: "#0f172a", borderRadius: 16, padding: 14, marginTop: 6 },
  reportTileLight: { backgroundColor: "#f8fafc", borderRadius: 16, padding: 14, marginTop: 10, borderWidth: 1, borderColor: "#e2e8f0" },
  reportTileK: { fontSize: 10, fontWeight: "900", color: "#93c5fd", textTransform: "uppercase", letterSpacing: 1.2 },
  reportTileTitle: { marginTop: 6, fontSize: 22, fontWeight: "900", color: "#fff" },
  reportTileMeta: { marginTop: 6, color: "rgba(255,255,255,0.72)", fontWeight: "700", lineHeight: 17 },
  reportTileTitleLight: { marginTop: 6, fontSize: 18, fontWeight: "900", color: "#0f172a" },
  reportTileMetaLight: { marginTop: 6, color: "#64748b", fontWeight: "700", lineHeight: 17 },
  categoryRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#f1f5f9" },
  catLabel: { flex: 1, fontSize: 13, fontWeight: "900", color: "#0f172a" },
  catAmount: { fontSize: 13, fontWeight: "900", color: "#16a34a" },
  catPct: { fontSize: 11, fontWeight: "900", color: "#64748b", marginTop: 3 },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: "#f1f5f9" },
  monthLabel: { fontSize: 13, fontWeight: "900", color: "#0f172a", flex: 1 },
  monthAmount: { fontSize: 13, fontWeight: "900", color: "#0f172a" },
  mutedText: { color: "#64748b", fontWeight: "900", fontSize: 12 },
  saveCard: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, backgroundColor: "#fff", gap: 10 },
  input: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 14, paddingHorizontal: 12, paddingVertical: 10, backgroundColor: "#fff" },
  primaryBtn: { backgroundColor: "#135bec", borderRadius: 14, paddingVertical: 12, paddingHorizontal: 14, alignItems: "center" },
  primaryBtnText: { color: "#fff", fontWeight: "900" },
});

