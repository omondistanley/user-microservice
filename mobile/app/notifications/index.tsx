import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Button, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";

type NotificationItem = {
  notification_id?: string | number;
  title?: string;
  body?: string;
  created_at?: string;
  is_read?: boolean;
};

function fmtCreatedAt(iso?: string): string {
  if (!iso) return "";
  return String(iso).replace("T", " ").slice(0, 16);
}

export default function NotificationsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [marking, setMarking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${GATEWAY_BASE_URL}/api/v1/notifications?page=1&page_size=30`;
      const res = await authClient.requestWithRefresh(url, { method: "GET" });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail(data?.detail, "Failed to load notifications."));
      }
      setUnread(Number(data?.unread ?? 0));
      setItems(Array.isArray(data?.items) ? data.items : []);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load notifications.");
      setItems([]);
      setUnread(0);
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
      const url = `${GATEWAY_BASE_URL}/api/v1/notifications/read-all`;
      await authClient.requestWithRefresh(url, { method: "PATCH" });
      await load();
    } catch {
      // no-op
    } finally {
      setMarking(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Notifications</Text>
        <View style={{ width: 60 }} />
      </View>

      <Text style={styles.unreadText}>{unread > 0 ? `${unread} unread` : "All read"}</Text>

      <View style={{ marginBottom: 8 }}>
        <Button title={marking ? "Working..." : "Mark all read"} onPress={markAllRead} disabled={marking || loading} />
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : items.length ? (
        items.map((it, idx) => {
          const isRead = Boolean(it.is_read);
          return (
            <View
              key={String(it.notification_id ?? idx)}
              style={[styles.row, !isRead ? styles.unreadRow : null]}
            >
              <Text style={styles.rowTitle}>{it.title ?? "Notification"}</Text>
              {it.body ? (
                <Text style={styles.rowBody} numberOfLines={3}>
                  {it.body}
                </Text>
              ) : null}
              {it.created_at ? <Text style={styles.rowMeta}>{fmtCreatedAt(it.created_at)}</Text> : null}
            </View>
          );
        })
      ) : (
        <Text style={styles.mutedText}>No notifications yet.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, gap: 10, backgroundColor: theme.colors.surface },
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backBtn: { width: 60 },
  backText: { color: theme.colors.primary, fontFamily: "Inter_700Bold" },
  title: { fontSize: 24, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  unreadText: { color: theme.colors.onSecondaryFixedVariant, fontSize: 12, fontFamily: "Inter_700Bold" },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold" },
  mutedText: { color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular" },
  row: {
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.surface,
    gap: 6,
  },
  unreadRow: { borderColor: theme.colors.primaryFixedDim, backgroundColor: theme.colors.primaryFixed },
  rowTitle: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  rowBody: { fontSize: 13, color: theme.colors.onSecondaryFixedVariant, fontFamily: "Inter_400Regular" },
  rowMeta: { fontSize: 12, color: theme.colors.onSurfaceVariant, fontFamily: "Inter_400Regular" },
});
