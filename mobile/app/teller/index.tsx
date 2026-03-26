import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { gatewayJson, gatewayUrl } from "../../src/gatewayRequest";
import { theme } from "../../src/theme";
import { Button } from "../../src/components/ui/Button";
import { formatApiDetail } from "../../src/formatApiDetail";

type Enrollment = { enrollment_id: string; institution_name?: string; created_at?: string };

export default function TellerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<Enrollment[]>([]);
  const [configured, setConfigured] = useState<boolean | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConfigured(null);
    try {
      const cfgRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/teller/config`, {
        method: "GET",
      });
      setConfigured(cfgRes.ok);
      if (!cfgRes.ok) {
        setItems([]);
        return;
      }
      const data = await gatewayJson<{ items?: Enrollment[] }>("/api/v1/teller/enrollments", { method: "GET" });
      setItems(Array.isArray(data?.items) ? data.items : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load Teller.");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const syncNow = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/teller/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const j = await res.json().catch(() => null);
      if (!res.ok) throw new Error(formatApiDetail(j?.detail, "Sync failed."));
      const created = typeof (j as { created?: number })?.created === "number" ? (j as { created: number }).created : null;
      Alert.alert("Teller sync", created != null ? `Imported ${created} transaction(s).` : "Sync completed.");
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  };

  const remove = (eid: string) => {
    Alert.alert("Remove enrollment", "Unlink this Teller connection?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: async () => {
          try {
            const res = await authClient.requestWithRefresh(
              gatewayUrl(`/api/v1/teller/enrollments/${encodeURIComponent(eid)}`),
              { method: "DELETE" },
            );
            const j = await res.json().catch(() => null);
            if (!res.ok) throw new Error(formatApiDetail(j?.detail, "Remove failed."));
            await load();
          } catch (err: unknown) {
            setError(err instanceof Error ? err.message : "Remove failed.");
          }
        },
      },
    ]);
  };

  return (
    <View style={[styles.root, { paddingTop: insets.top, backgroundColor: theme.colors.background }]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Teller (EU banks)</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 40 }}>
        <Text style={styles.body}>
          Same REST API as the web app: list enrollments, sync transactions to expenses, remove enrollment. First-time
          linking uses Teller Connect in the browser.
        </Text>
        <Button title="Open gateway (complete link in browser)" tone="secondary" onPress={() => Linking.openURL(GATEWAY_BASE_URL)} />
        <View style={{ height: 12 }} />
        {loading ? (
          <ActivityIndicator color={theme.colors.primary} />
        ) : configured === false ? (
          <Text style={styles.warn}>Teller is not configured on this server (503 on /teller/config).</Text>
        ) : error ? (
          <Text style={styles.err}>{error}</Text>
        ) : null}

        {!loading && configured ? (
          <>
            <Button title="Sync transactions now" onPress={syncNow} loading={syncing} disabled={syncing} />
            <Text style={[styles.sub, { marginTop: 12 }]}>Enrollments</Text>
            {items.length ? (
              items.map((it) => (
                <View key={it.enrollment_id} style={styles.card}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.bank}>{it.institution_name ?? "Linked account"}</Text>
                    <Text style={styles.meta}>{it.enrollment_id}</Text>
                  </View>
                  <Pressable onPress={() => remove(it.enrollment_id)} hitSlop={10}>
                    <MaterialCommunityIcons name="delete-outline" size={22} color={theme.colors.error} />
                  </Pressable>
                </View>
              ))
            ) : (
              <Text style={styles.muted}>No enrollments yet. Link via web Teller Connect, then return here to sync.</Text>
            )}
          </>
        ) : null}

        <Pressable style={{ marginTop: 20 }} onPress={load}>
          <Text style={styles.link}>Refresh</Text>
        </Pressable>
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
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.outlineVariant,
  },
  title: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  body: { color: theme.colors.onSurfaceVariant, lineHeight: 20, marginBottom: 12, fontSize: 13 },
  sub: { fontFamily: "Inter_800ExtraBold", fontSize: 12, color: theme.colors.secondary, textTransform: "uppercase" },
  card: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    marginTop: 10,
  },
  bank: { fontFamily: "Inter_700Bold", fontSize: 15, color: theme.colors.onSurface },
  meta: { fontSize: 11, color: theme.colors.secondary, marginTop: 4 },
  muted: { color: theme.colors.secondary, marginTop: 8 },
  warn: { color: "#b45309", fontFamily: "Inter_600SemiBold", marginTop: 8 },
  err: { color: theme.colors.error, marginTop: 8 },
  link: { color: theme.colors.primary, fontFamily: "Inter_700Bold" },
});
