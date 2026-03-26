import React, { useCallback, useEffect, useState } from "react";
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
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { gatewayJson, gatewayUrl } from "../../src/gatewayRequest";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { formatApiDetail } from "../../src/formatApiDetail";

type Item = {
  watchlist_id: number;
  symbol: string;
  target_price?: number | null;
  direction?: string;
  notes?: string | null;
  created_at?: string;
};

export default function WatchlistScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [modal, setModal] = useState(false);
  const [sym, setSym] = useState("");
  const [target, setTarget] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("below");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await gatewayJson<{ items?: Item[] }>("/api/v1/watchlist", { method: "GET" });
      setItems(Array.isArray(data?.items) ? data.items : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load watchlist.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const add = async () => {
    const symbol = sym.trim().toUpperCase();
    if (!symbol) {
      setError("Enter a symbol.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { symbol, direction };
      const t = Number(String(target).replace(/,/g, ""));
      if (target.trim() && Number.isFinite(t)) body.target_price = t;
      if (notes.trim()) body.notes = notes.trim().slice(0, 512);
      await gatewayJson("/api/v1/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setModal(false);
      setSym("");
      setTarget("");
      setNotes("");
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Add failed.");
    } finally {
      setSaving(false);
    }
  };

  const remove = (it: Item) => {
    Alert.alert("Remove", `Remove ${it.symbol} from watchlist?`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Remove",
        style: "destructive",
        onPress: async () => {
          try {
            const res = await authClient.requestWithRefresh(
              gatewayUrl(`/api/v1/watchlist/${encodeURIComponent(String(it.watchlist_id))}`),
              { method: "DELETE" },
            );
            if (!res.ok) {
              const j = await res.json().catch(() => null);
              throw new Error(formatApiDetail(j?.detail, "Delete failed."));
            }
            await load();
          } catch (e: unknown) {
            setError(e instanceof Error ? e.message : "Delete failed.");
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
        <Text style={styles.title}>Watchlist</Text>
        <Pressable hitSlop={12} onPress={() => setModal(true)}>
          <MaterialCommunityIcons name="plus" size={26} color={theme.colors.primary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 40 }}>
        <Text style={styles.disclaimer}>
          Price alerts are informational only — not financial advice. Matches web watchlist API.
        </Text>
        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={theme.colors.primary} />
        ) : error ? (
          <Text style={styles.err}>{error}</Text>
        ) : items.length ? (
          items.map((it) => (
            <Pressable key={String(it.watchlist_id)} style={styles.card} onPress={() => remove(it)}>
              <View style={{ flex: 1 }}>
                <Text style={styles.sym}>{it.symbol}</Text>
                {it.target_price != null ? (
                  <Text style={styles.meta}>
                    Alert {it.direction === "above" ? "above" : "below"} {it.target_price}
                  </Text>
                ) : null}
                {it.notes ? <Text style={styles.meta}>{it.notes}</Text> : null}
              </View>
              <MaterialCommunityIcons name="delete-outline" size={22} color={theme.colors.error} />
            </Pressable>
          ))
        ) : (
          <Text style={styles.muted}>No symbols yet. Tap + to add one.</Text>
        )}
      </ScrollView>

      <Modal visible={modal} transparent animationType="slide">
        <View style={styles.backdrop}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>Add symbol</Text>
            <Input placeholder="AAPL" value={sym} onChangeText={setSym} autoCapitalize="characters" />
            <Text style={styles.lbl}>Target price (optional)</Text>
            <Input value={target} onChangeText={setTarget} keyboardType="decimal-pad" placeholder="180" />
            <Text style={styles.lbl}>Direction</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              {(["below", "above"] as const).map((d) => (
                <Pressable
                  key={d}
                  onPress={() => setDirection(d)}
                  style={[styles.chip, direction === d && styles.chipOn]}
                >
                  <Text style={[styles.chipTxt, direction === d && styles.chipTxtOn]}>{d}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.lbl}>Notes (optional)</Text>
            <Input value={notes} onChangeText={setNotes} placeholder="Reason" />
            <View style={{ flexDirection: "row", gap: 10, marginTop: 16 }}>
              <View style={{ flex: 1 }}>
                <Button title="Cancel" tone="secondary" onPress={() => setModal(false)} disabled={saving} />
              </View>
              <View style={{ flex: 1 }}>
                <Button title="Save" onPress={add} loading={saving} disabled={saving} />
              </View>
            </View>
          </View>
        </View>
      </Modal>
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
  title: { fontSize: 18, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  disclaimer: { fontSize: 11, color: theme.colors.secondary, marginBottom: 12, lineHeight: 16 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    padding: 14,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    marginBottom: 10,
  },
  sym: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  meta: { fontSize: 12, color: theme.colors.onSurfaceVariant, marginTop: 4 },
  muted: { color: theme.colors.secondary, marginTop: 8 },
  err: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "center",
    padding: 20,
  },
  modal: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.lg, padding: 18, gap: 8 },
  modalTitle: { fontSize: 18, fontFamily: "Inter_800ExtraBold", marginBottom: 8 },
  lbl: { fontSize: 12, fontFamily: "Inter_700Bold", color: theme.colors.onSurfaceVariant, marginTop: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  chipOn: { backgroundColor: theme.colors.primary, borderColor: theme.colors.primary },
  chipTxt: { fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  chipTxtOn: { color: theme.colors.onPrimary },
});
