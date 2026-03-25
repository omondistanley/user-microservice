import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type SavedViewItem = {
  view_id?: string;
  name?: string;
  payload?: any;
  created_at?: string;
  updated_at?: string;
};

type SavedViewsResponse = {
  items?: SavedViewItem[];
};

export default function SavedViewsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<SavedViewItem[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/reports/saved-views`, { method: "GET" });
      const json = (await res.json().catch(() => null)) as SavedViewsResponse | null;
      if (!res.ok) throw new Error(json ? (json as any)?.detail ? String((json as any).detail) : "Failed to load saved views." : "Failed to load saved views.");
      setItems(Array.isArray(json?.items) ? (json!.items as SavedViewItem[]) : []);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load saved views.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const deleteView = async (viewId: string) => {
    setDeletingId(viewId);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/reports/saved-views/${encodeURIComponent(viewId)}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const json = await res.json().catch(() => null);
        throw new Error(json?.detail ? String(json.detail) : "Delete failed.");
      }
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Delete failed.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Saved Views</Text>
        <View style={{ width: 60 }} />
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        <View style={styles.list}>
          {items.map((it, idx) => {
            const id = it.view_id ? String(it.view_id) : String(idx);
            const payload = it.payload ?? {};
            const period = payload.period ? String(payload.period) : "—";
            const ccy = payload.currency ? String(payload.currency) : "—";
            const dateFrom = payload.date_from ? String(payload.date_from).slice(0, 10) : "";
            const dateTo = payload.date_to ? String(payload.date_to).slice(0, 10) : "";
            return (
              <View key={id} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name} numberOfLines={1}>
                    {it.name ?? "Untitled"}
                  </Text>
                  <Text style={styles.meta}>
                    {period} • {ccy}
                    {dateFrom && dateTo ? ` • ${dateFrom} → ${dateTo}` : ""}
                  </Text>
                </View>

                <Pressable
                  disabled={deletingId === id}
                  onPress={() => deleteView(id)}
                  style={[styles.deleteBtn, deletingId === id ? styles.deleteBtnDisabled : null]}
                >
                  <Text style={styles.deleteText}>{deletingId === id ? "Deleting..." : "Delete"}</Text>
                </Pressable>
              </View>
            );
          })}
        </View>
      ) : (
        <Text style={styles.mutedText}>No saved views yet. Create one in `Reports`.</Text>
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
  errorText: { color: "#dc2626", fontWeight: "900" },
  mutedText: { color: "#64748b", fontWeight: "900" },
  list: { gap: 10 },
  row: {
    flexDirection: "row",
    gap: 10,
    padding: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    alignItems: "center",
    backgroundColor: "#fff",
  },
  name: { fontSize: 14, fontWeight: "900", color: "#0f172a", flex: 1 },
  meta: { marginTop: 4, fontSize: 12, fontWeight: "900", color: "#64748b" },
  deleteBtn: { backgroundColor: "#fee2e2", borderWidth: 1, borderColor: "#fca5a5", borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  deleteBtnDisabled: { opacity: 0.7 },
  deleteText: { color: "#0f172a", fontWeight: "900" },
});

