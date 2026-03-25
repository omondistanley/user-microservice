import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

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

export default function NetWorthBreakdownScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assets, setAssets] = useState<Record<string, unknown>[]>([]);
  const [liabs, setLiabs] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [aRes, lRes] = await Promise.all([
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/assets`, { method: "GET" }),
          authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/net-worth/liabilities`, { method: "GET" }),
        ]);
        const aJson = await aRes.json().catch(() => null);
        const lJson = await lRes.json().catch(() => null);
        if (!aRes.ok) {
          throw new Error((aJson as any)?.detail ? String((aJson as any).detail) : "Failed to load assets.");
        }
        if (!lRes.ok) {
          throw new Error((lJson as any)?.detail ? String((lJson as any).detail) : "Failed to load liabilities.");
        }
        if (cancelled) return;
        setAssets(Array.isArray(aJson) ? aJson : []);
        setLiabs(Array.isArray(lJson) ? lJson : []);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Failed to load breakdown.");
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <View style={[styles.root, { paddingTop: insets.top, backgroundColor: theme.colors.surfaceDim }]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="chevron-left" size={28} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Net worth breakdown</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + 24 }]}>
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
                <View key={String((row as any).id ?? idx)} style={styles.row}>
                  <MaterialCommunityIcons name="bank" size={22} color={theme.colors.primary} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{String((row as any).name ?? (row as any).label ?? "Asset")}</Text>
                    <Text style={styles.rowMeta}>{String((row as any).asset_type ?? (row as any).type ?? "")}</Text>
                  </View>
                  <Text style={styles.rowAmt}>{fmtMoney((row as any).value ?? (row as any).amount)}</Text>
                </View>
              ))
            )}

            <Text style={[styles.section, { marginTop: 24 }]}>Liabilities</Text>
            {liabs.length === 0 ? (
              <Text style={styles.empty}>No manual liabilities recorded.</Text>
            ) : (
              liabs.map((row, idx) => (
                <View key={String((row as any).id ?? idx)} style={styles.row}>
                  <MaterialCommunityIcons name="credit-card-outline" size={22} color={theme.colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{String((row as any).name ?? (row as any).label ?? "Liability")}</Text>
                    <Text style={styles.rowMeta}>{String((row as any).liability_type ?? (row as any).type ?? "")}</Text>
                  </View>
                  <Text style={[styles.rowAmt, { color: theme.colors.error }]}>
                    -{fmtMoney((row as any).value ?? (row as any).amount ?? (row as any).balance)}
                  </Text>
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
