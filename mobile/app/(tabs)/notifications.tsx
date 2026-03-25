import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Button, ScrollView, StyleSheet, Text, View } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

export default function NotificationsScreen() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState<number>(0);
  const [items, setItems] = useState<any[]>([]);
  const [marking, setMarking] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/notifications?page=1&page_size=20`,
        { method: "GET" },
      );
      const data = await res.json().catch(() => null);
      const list = data?.items && Array.isArray(data.items) ? data.items : [];
      setUnread(Number(data?.unread ?? 0));
      setItems(list);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load notifications.");
      setUnread(0);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const markAllRead = async () => {
    setMarking(true);
    try {
      await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/notifications/read-all`,
        { method: "PATCH" },
      );
      await load();
    } catch {
      // keep existing state; show generic error at top if needed
    } finally {
      setMarking(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Notifications</Text>
        <Text style={styles.unreadText}>{unread > 0 ? `${unread} unread` : "All read"}</Text>
      </View>

      <View style={{ marginBottom: 10 }}>
        <Button title={marking ? "Working..." : "Mark all read"} onPress={markAllRead} disabled={marking || loading} />
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it: any) => {
          const title = String(it?.title || "Notification");
          const body = String(it?.body || "");
          const isRead = Boolean(it?.is_read);
          const createdAt = it?.created_at ? String(it.created_at).slice(0, 16) : "";
          return (
            <View key={String(it?.notification_id ?? title + createdAt)} style={[styles.row, !isRead ? styles.unreadRow : null]}>
              <Text style={styles.rowTitle}>{title}</Text>
              {body ? (
                <Text style={styles.rowBody} numberOfLines={3}>
                  {body}
                </Text>
              ) : null}
              {createdAt ? <Text style={styles.rowMeta}>{createdAt}</Text> : null}
            </View>
          );
        })
      ) : (
        <Text style={styles.cardText}>No notifications yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 10 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  title: { fontSize: 22, fontWeight: "700" },
  unreadText: { color: "#334155", fontSize: 12, fontWeight: "700" },
  errorText: { color: "#dc2626" },
  cardText: { color: "#334155", marginTop: 6 },
  row: {
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    backgroundColor: "#fff",
  },
  unreadRow: { borderColor: "#93c5fd", backgroundColor: "#eff6ff" },
  rowTitle: { fontSize: 14, fontWeight: "800", color: "#0f172a" },
  rowBody: { fontSize: 13, color: "#334155", marginTop: 6 },
  rowMeta: { fontSize: 12, color: "#64748b", marginTop: 6 },
});

