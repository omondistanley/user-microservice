import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";

function toNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v));
  return Number.isFinite(n) ? n : null;
}

function getDisplayKey(row: Record<string, unknown>, idx: number): string {
  return String(row.asset_id ?? row.liability_id ?? row.id ?? idx);
}

function liabilityDisplayMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `-${fmtMoney(Math.abs(n))}`;
}

function fmtMoney(v: unknown): string {
  const n = toNumber(v);
  if (n === null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function NetWorthBreakdownScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assets, setAssets] = useState<Record<string, unknown>[]>([]);
  const [liabs, setLiabs] = useState<Record<string, unknown>[]>([]);
  const [entryType, setEntryType] = useState<"asset" | "liability">("asset");
  const [name, setName] = useState("");
  const [type, setType] = useState("");
  const [value, setValue] = useState("");

  const loadBreakdown = useCallback(async (isPullRefresh = false) => {
    if (isPullRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [aRes, lRes] = await Promise.all([
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/assets`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/liabilities`, { method: "GET" }),
      ]);
      const aJson = await aRes.json().catch(() => null);
      const lJson = await lRes.json().catch(() => null);
      if (!aRes.ok) {
        throw new Error(formatApiDetail((aJson as any)?.detail, "Failed to load assets."));
      }
      if (!lRes.ok) {
        throw new Error(formatApiDetail((lJson as any)?.detail, "Failed to load liabilities."));
      }
      setAssets(Array.isArray(aJson) ? aJson : []);
      setLiabs(Array.isArray(lJson) ? lJson : []);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load breakdown.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadBreakdown();
    }, [loadBreakdown]),
  );

  const resetForm = () => {
    setName("");
    setType("");
    setValue("");
  };

  const saveEntry = async () => {
    const cleanedName = name.trim();
    const cleanedType = type.trim();
    const amount = toNumber(value);
    if (!cleanedName || !cleanedType || amount === null || amount < 0) {
      setError("Enter a name, type, and non-negative amount.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const endpoint =
        entryType === "asset"
          ? `${GATEWAY_BASE_URL}/api/v1/net-worth/assets`
          : `${GATEWAY_BASE_URL}/api/v1/net-worth/liabilities`;
      const res = await authClient.requestWithRefresh(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: cleanedName,
          type: cleanedType,
          value: amount,
          currency: "USD",
        }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        const fallback = entryType === "asset" ? "Failed to save asset." : "Failed to save liability.";
        throw new Error(formatApiDetail((json as any)?.detail, fallback));
      }
      resetForm();
      await loadBreakdown();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to save entry.");
    } finally {
      setSubmitting(false);
    }
  };

  const deleteEntry = async (kind: "asset" | "liability", id: string) => {
    const endpoint =
      kind === "asset"
        ? `${GATEWAY_BASE_URL}/api/v1/net-worth/assets/${id}`
        : `${GATEWAY_BASE_URL}/api/v1/net-worth/liabilities/${id}`;
    try {
      const res = await authClient.requestWithRefresh(endpoint, { method: "DELETE" });
      if (!res.ok && res.status !== 204) {
        const json = await res.json().catch(() => null);
        const fallback = kind === "asset" ? "Failed to delete asset." : "Failed to delete liability.";
        throw new Error(formatApiDetail((json as any)?.detail, fallback));
      }
      await loadBreakdown();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to delete entry.");
    }
  };

  const promptDelete = (kind: "asset" | "liability", row: Record<string, unknown>) => {
    const id = String((row as any).asset_id ?? (row as any).liability_id ?? "");
    if (!id) return;
    const title = kind === "asset" ? "Delete asset?" : "Delete liability?";
    const label = String((row as any).name ?? (row as any).label ?? "this item");
    Alert.alert(title, `Remove ${label}?`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => deleteEntry(kind, id) },
    ]);
  };

  return (
    <View
      style={[styles.root, { paddingTop: insets.top, backgroundColor: theme.colors.surfaceDim }]}
      testID="e2e-networth-breakdown-screen"
    >
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="chevron-left" size={28} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Net worth breakdown</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadBreakdown(true)} />}
      >
        <View style={styles.actionsRow}>
          <Pressable
            style={[styles.toggleBtn, entryType === "asset" && styles.toggleBtnOn]}
            onPress={() => setEntryType("asset")}
            testID="e2e-networth-type-asset"
          >
            <Text style={[styles.toggleBtnTxt, entryType === "asset" && styles.toggleBtnTxtOn]}>Asset</Text>
          </Pressable>
          <Pressable
            style={[styles.toggleBtn, entryType === "liability" && styles.toggleBtnOn]}
            onPress={() => setEntryType("liability")}
            testID="e2e-networth-type-liability"
          >
            <Text style={[styles.toggleBtnTxt, entryType === "liability" && styles.toggleBtnTxtOn]}>Liability</Text>
          </Pressable>
        </View>

        <View style={styles.formCard}>
          <Text style={styles.formTitle}>{entryType === "asset" ? "Add manual asset" : "Add manual liability"}</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            style={styles.input}
            placeholder="Name"
            placeholderTextColor={theme.colors.onSurfaceVariant}
            testID="e2e-networth-name"
          />
          <TextInput
            value={type}
            onChangeText={setType}
            style={styles.input}
            placeholder="Type"
            placeholderTextColor={theme.colors.onSurfaceVariant}
            testID="e2e-networth-type"
          />
          <TextInput
            value={value}
            onChangeText={setValue}
            style={styles.input}
            placeholder="Amount"
            placeholderTextColor={theme.colors.onSurfaceVariant}
            keyboardType="decimal-pad"
            testID="e2e-networth-value"
          />
          <Pressable
            style={[styles.saveBtn, submitting && styles.saveBtnDisabled]}
            onPress={saveEntry}
            disabled={submitting}
            testID="e2e-networth-save"
          >
            {submitting ? (
              <ActivityIndicator color={theme.colors.onPrimary} />
            ) : (
              <Text style={styles.saveBtnTxt}>Save {entryType}</Text>
            )}
          </Pressable>
        </View>

        {loading ? (
          <ActivityIndicator style={{ marginTop: 32 }} />
        ) : error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <>
            <Text style={styles.section}>Assets</Text>
            {assets.length === 0 ? (
              <Text style={styles.empty}>No manual assets recorded.</Text>
            ) : (
              assets.map((row, idx) => (
                <View key={getDisplayKey(row, idx)} style={styles.row}>
                  <MaterialCommunityIcons name="bank" size={22} color={theme.colors.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{String((row as any).name ?? (row as any).label ?? "Asset")}</Text>
                    <Text style={styles.rowMeta}>{String((row as any).asset_type ?? (row as any).type ?? "")}</Text>
                  </View>
                  <Text style={styles.rowAmt}>{fmtMoney((row as any).value ?? (row as any).amount)}</Text>
                  <Pressable hitSlop={8} onPress={() => promptDelete("asset", row)}>
                    <MaterialCommunityIcons name="trash-can-outline" size={18} color={theme.colors.error} />
                  </Pressable>
                </View>
              ))
            )}

            <Text style={[styles.section, { marginTop: 24 }]}>Liabilities</Text>
            {liabs.length === 0 ? (
              <Text style={styles.empty}>No manual liabilities recorded.</Text>
            ) : (
              liabs.map((row, idx) => (
                <View key={getDisplayKey(row, idx)} style={styles.row}>
                  <MaterialCommunityIcons name="credit-card-outline" size={22} color={theme.colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{String((row as any).name ?? (row as any).label ?? "Liability")}</Text>
                    <Text style={styles.rowMeta}>{String((row as any).liability_type ?? (row as any).type ?? "")}</Text>
                  </View>
                  <Text style={[styles.rowAmt, { color: theme.colors.error }]}> 
                    {liabilityDisplayMoney((row as any).value ?? (row as any).amount ?? (row as any).balance)}
                  </Text>
                  <Pressable hitSlop={8} onPress={() => promptDelete("liability", row)}>
                    <MaterialCommunityIcons name="trash-can-outline" size={18} color={theme.colors.error} />
                  </Pressable>
                </View>
              ))
            )}
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
  scroll: { padding: theme.spacing.xl, gap: 10 },
  actionsRow: {
    flexDirection: "row",
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: 999,
    padding: 4,
    gap: 6,
  },
  toggleBtn: {
    flex: 1,
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: "center",
  },
  toggleBtnOn: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  toggleBtnTxt: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.secondary },
  toggleBtnTxtOn: { color: theme.colors.onSurface },
  formCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    gap: 10,
  },
  formTitle: { fontSize: 15, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  input: {
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: theme.radii.md,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: theme.colors.onSurface,
    fontFamily: "Inter_400Regular",
  },
  saveBtn: {
    marginTop: 4,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  saveBtnDisabled: { opacity: 0.7 },
  saveBtnTxt: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 14 },
  section: { fontSize: 12, fontFamily: "Inter_800ExtraBold", color: theme.colors.secondary, letterSpacing: 1.2, textTransform: "uppercase" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: 14,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  rowTitle: { fontSize: 15, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  rowMeta: { fontSize: 12, color: theme.colors.secondary, marginTop: 2 },
  rowAmt: { fontSize: 15, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  empty: { color: theme.colors.secondary, fontFamily: "Inter_400Regular" },
  error: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
});
