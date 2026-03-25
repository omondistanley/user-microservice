import React, { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import * as AuthTokens from "../../src/authTokens";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { Screen } from "../../src/components/ui/Screen";
import { TopBar } from "../../src/components/ui/TopBar";
import { Card } from "../../src/components/ui/Card";
import { Text } from "../../src/components/ui/Text";
import { Button } from "../../src/components/ui/Button";
import { theme } from "../../src/theme";

type SessionItem = {
  session_id?: string;
  device_meta?: any;
  issued_at?: string;
  last_seen_at?: string;
};

type SessionsResponse = { items?: SessionItem[] };

function fmtWhen(iso?: string): string {
  if (!iso) return "—";
  return String(iso).slice(0, 10);
}

export default function SessionsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<SessionItem[]>([]);
  const [revoking, setRevoking] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const json = await authClient.requestJsonWithRefresh<SessionsResponse>(`${GATEWAY_BASE_URL}/api/v1/sessions`, { method: "GET" });
      setItems(Array.isArray(json?.items) ? (json.items as SessionItem[]) : []);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load sessions.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const revokeAllExceptCurrent = async () => {
    setRevoking(true);
    setError(null);
    try {
      const refreshToken = await AuthTokens.getRefreshToken();
      if (!refreshToken) throw new Error("No refresh token available.");

      await authClient.requestJsonWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/sessions/revoke-all-except-current`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
      );
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to revoke sessions.");
    } finally {
      setRevoking(false);
    }
  };

  return (
    <Screen>
      <TopBar title="Sessions" onBack={() => router.back()} />

      <Card>
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Trusted devices
        </Text>
        <Text color={theme.colors.onSurfaceVariant}>Active sessions for your account (except revoked ones).</Text>

        <View style={{ marginTop: 12 }}>
          <Button title="Revoke all except current" tone="danger" loading={revoking} onPress={revokeAllExceptCurrent} />
        </View>
      </Card>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text color={theme.colors.error}>{error}</Text>
      ) : items.length ? (
        <View style={styles.list}>
          {items.map((s, idx) => {
            const id = s.session_id ? String(s.session_id) : String(idx);
            const deviceName =
              (typeof s.device_meta === "object" && s.device_meta && (s.device_meta as any).name) ||
              (typeof s.device_meta === "object" && s.device_meta && (s.device_meta as any).device_name) ||
              null;
            return (
              <View key={id} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>{deviceName ?? "Session"}</Text>
                  <Text style={styles.rowMeta}>Issued: {fmtWhen(s.issued_at)}</Text>
                  <Text style={styles.rowMeta}>Last seen: {fmtWhen(s.last_seen_at)}</Text>
                </View>
                <Text style={styles.sessionId}>{id.slice(0, 8)}…</Text>
              </View>
            );
          })}
        </View>
      ) : (
        <Text color={theme.colors.onSurfaceVariant}>No active sessions found.</Text>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: 10 },
  row: { flexDirection: "row", gap: 10, borderWidth: 1, borderColor: theme.colors.outlineVariant, borderRadius: 16, padding: 12, backgroundColor: theme.colors.surface, alignItems: "center" },
  rowTitle: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface, flex: 1 },
  rowMeta: { fontSize: 12, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurfaceVariant, marginTop: 4 },
  sessionId: { fontSize: 11, fontFamily: "Inter_700Bold", color: "#475569" },
});

