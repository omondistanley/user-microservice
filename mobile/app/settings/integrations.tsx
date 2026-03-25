import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type PlaidItem = {
  item_id?: string;
  institution_name?: string;
  created_at?: string;
};

type PlaidItemsResponse = { items?: PlaidItem[] };
type PlaidAccount = {
  account_id?: string;
  item_id?: string;
  institution_name?: string;
  name?: string;
  official_name?: string;
  mask?: string;
  type?: string;
  subtype?: string;
};
type PlaidAccountsResponse = { accounts?: PlaidAccount[] };

type CalendarStatus = {
  connected?: boolean;
  enabled?: boolean;
  provider?: string;
  provider_account_email?: string | null;
  provider_calendar_id?: string | null;
  token_expires_at?: string | null;
  last_synced_at?: string | null;
};
type CalendarAuthorizeResponse = {
  authorization_url?: string;
  provider?: string;
};

type AlpacaStatus = {
  connected?: boolean;
  alpaca_account_id?: string | null;
  is_paper?: boolean;
  last_sync_at?: string | null;
};

export default function IntegrationsScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [items, setItems] = useState<PlaidItem[]>([]);
  const [accounts, setAccounts] = useState<PlaidAccount[]>([]);
  const [syncingPlaid, setSyncingPlaid] = useState(false);

  const [calendar, setCalendar] = useState<CalendarStatus | null>(null);
  const [calendarBusy, setCalendarBusy] = useState(false);

  const [alpaca, setAlpaca] = useState<AlpacaStatus | null>(null);
  const [alpacaBusy, setAlpacaBusy] = useState(false);
  const [alpacaApiKeyId, setAlpacaApiKeyId] = useState("");
  const [alpacaApiKeySecret, setAlpacaApiKeySecret] = useState("");
  const [alpacaPaper, setAlpacaPaper] = useState(true);
  const [deletingPlaidItemId, setDeletingPlaidItemId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [itemsRes, accountsRes, calendarRes, alpacaRes] = await Promise.all([
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/items`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/accounts`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/calendar/status`, { method: "GET" }),
        authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/alpaca/status`, { method: "GET" }),
      ]);

      const itemsJson = (await itemsRes.json().catch(() => null)) as PlaidItemsResponse | null;
      const accountsJson = (await accountsRes.json().catch(() => null)) as PlaidAccountsResponse | null;
      const calendarJson = (await calendarRes.json().catch(() => null)) as CalendarStatus | null;
      const alpacaJson = (await alpacaRes.json().catch(() => null)) as AlpacaStatus | null;

      if (!itemsRes.ok) {
        throw new Error((itemsJson as any)?.detail ? String((itemsJson as any).detail) : "Failed to load Plaid items.");
      }
      if (!accountsRes.ok) {
        throw new Error(
          (accountsJson as any)?.detail ? String((accountsJson as any).detail) : "Failed to load Plaid accounts.",
        );
      }
      if (!calendarRes.ok) {
        throw new Error(
          (calendarJson as any)?.detail ? String((calendarJson as any).detail) : "Failed to load calendar status.",
        );
      }
      if (!alpacaRes.ok) {
        throw new Error((alpacaJson as any)?.detail ? String((alpacaJson as any).detail) : "Failed to load Alpaca status.");
      }

      setItems(Array.isArray(itemsJson?.items) ? (itemsJson.items as PlaidItem[]) : []);
      setAccounts(Array.isArray(accountsJson?.accounts) ? (accountsJson.accounts as PlaidAccount[]) : []);
      setCalendar(calendarJson ?? null);
      setAlpaca(alpacaJson ?? { connected: false });
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load integrations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectCalendar = async () => {
    setCalendarBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/calendar/oauth/authorize?provider=google&json=1`,
        { method: "GET" },
      );
      const json = (await res.json().catch(() => null)) as CalendarAuthorizeResponse | null;
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Calendar connect failed.");
      }
      const authUrl = json?.authorization_url ? String(json.authorization_url) : "";
      if (!authUrl) {
        throw new Error("Calendar authorization URL missing.");
      }
      await WebBrowser.openBrowserAsync(authUrl);
      setMessage("Complete Google Calendar consent in browser, then tap Refresh.");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Calendar connect failed.");
    } finally {
      setCalendarBusy(false);
    }
  };

  const disconnectCalendar = async () => {
    setCalendarBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/calendar/disconnect`, {
        method: "DELETE",
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Calendar disconnect failed.");
      }
      setMessage("Calendar disconnected.");
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Calendar disconnect failed.");
    } finally {
      setCalendarBusy(false);
    }
  };

  const connectAlpaca = async () => {
    setAlpacaBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/alpaca/link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key_id: alpacaApiKeyId.trim(),
          api_key_secret: alpacaApiKeySecret.trim(),
          is_paper: alpacaPaper,
        }),
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Alpaca link failed.");
      }
      setMessage("Alpaca linked.");
      setAlpacaApiKeyId("");
      setAlpacaApiKeySecret("");
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Alpaca link failed.");
    } finally {
      setAlpacaBusy(false);
    }
  };

  const syncAlpaca = async () => {
    setAlpacaBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/alpaca/sync`, { method: "POST" });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Alpaca sync failed.");
      }
      setMessage(`Alpaca sync complete${typeof json?.synced === "number" ? ` (${json.synced} positions)` : ""}.`);
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Alpaca sync failed.");
    } finally {
      setAlpacaBusy(false);
    }
  };

  const unlinkAlpaca = async () => {
    setAlpacaBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/alpaca/link`, {
        method: "DELETE",
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Alpaca unlink failed.");
      }
      setMessage("Alpaca disconnected.");
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Alpaca unlink failed.");
    } finally {
      setAlpacaBusy(false);
    }
  };

  const syncPlaid = async () => {
    setSyncingPlaid(true);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/sync`, { method: "POST" });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Plaid sync failed.");
      }
      setMessage(`Plaid sync complete${typeof json?.created === "number" ? ` (${json.created} transactions)` : ""}.`);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Plaid sync failed.");
    } finally {
      setSyncingPlaid(false);
    }
  };

  const deletePlaidItem = async (itemId: string) => {
    setDeletingPlaidItemId(itemId);
    setError(null);
    setMessage(null);
    try {
      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/items/${encodeURIComponent(itemId)}`, {
        method: "DELETE",
      });
      const json = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to unlink bank item.");
      }
      setMessage("Bank item removed.");
      await load();
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to unlink bank item.");
    } finally {
      setDeletingPlaidItemId(null);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Integrations</Text>
        <Pressable style={styles.secondaryBtn} onPress={load} disabled={loading}>
          <Text style={styles.secondaryBtnText}>{loading ? "Refreshing…" : "Refresh"}</Text>
        </Pressable>
      </View>

      {message ? <Text style={styles.infoText}>{message}</Text> : null}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>Plaid bank link</Text>
          <Pressable style={styles.primaryBtn} onPress={() => router.push("/link-bank")}>
            <Text style={styles.primaryBtnText}>Connect</Text>
          </Pressable>
        </View>
        <Pressable style={styles.secondaryBtn} onPress={syncPlaid} disabled={syncingPlaid}>
          <Text style={styles.secondaryBtnText}>{syncingPlaid ? "Syncing…" : "Sync transactions now"}</Text>
        </Pressable>

        {loading ? (
          <ActivityIndicator />
        ) : items.length ? (
          <>
            <Text style={styles.subText}>Linked items: {items.length}</Text>
            <View style={styles.list}>
              {items.map((it, idx) => (
                <View key={`${String(it.item_id ?? "item")}-${idx}`} style={styles.listRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.listName} numberOfLines={1}>
                      {it.institution_name ?? "Linked account"}
                    </Text>
                    {it.created_at ? <Text style={styles.listMeta}>Added {String(it.created_at).slice(0, 10)}</Text> : null}
                  </View>
                  {it.item_id ? (
                    <Pressable
                      style={styles.dangerBtn}
                      onPress={() => deletePlaidItem(String(it.item_id))}
                      disabled={deletingPlaidItemId === String(it.item_id)}
                    >
                      <Text style={styles.dangerBtnText}>
                        {deletingPlaidItemId === String(it.item_id) ? "Removing…" : "Remove"}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              ))}
            </View>
            <Text style={styles.subText}>Detected Plaid accounts: {accounts.length}</Text>
            {accounts.length ? (
              <View style={styles.list}>
                {accounts.slice(0, 6).map((acct, idx) => (
                  <View key={`${String(acct.account_id ?? "account")}-${idx}`} style={styles.listRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.listName} numberOfLines={1}>
                        {acct.name ?? acct.official_name ?? "Account"}
                      </Text>
                      <Text style={styles.listMeta} numberOfLines={1}>
                        {acct.institution_name ?? "Bank"} • {acct.type ?? "type"} / {acct.subtype ?? "subtype"}
                        {acct.mask ? ` • ****${acct.mask}` : ""}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            ) : (
              <Text style={styles.mutedText}>No account metadata yet. Complete a Plaid connection first.</Text>
            )}
          </>
        ) : (
          <Text style={styles.mutedText}>No linked accounts yet. Connect a bank to import transactions.</Text>
        )}
      </View>

      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>Google Calendar</Text>
          {calendar?.connected ? (
            <View style={styles.pillOk}>
              <Text style={styles.pillOkText}>Connected</Text>
            </View>
          ) : (
            <View style={styles.pillMuted}>
              <Text style={styles.pillMutedText}>Not connected</Text>
            </View>
          )}
        </View>
        <Text style={styles.mutedText}>
          {calendar?.connected
            ? `Connected as ${calendar.provider_account_email ?? "your account"}.`
            : "Connect Google Calendar to mirror web reminder integrations."}
        </Text>
        <View style={styles.btnRow}>
          <Pressable style={styles.secondaryBtn} onPress={connectCalendar} disabled={calendarBusy}>
            <Text style={styles.secondaryBtnText}>{calendarBusy ? "Opening…" : "Connect calendar"}</Text>
          </Pressable>
          {calendar?.connected ? (
            <Pressable style={styles.dangerBtn} onPress={disconnectCalendar} disabled={calendarBusy}>
              <Text style={styles.dangerBtnText}>{calendarBusy ? "Disconnecting…" : "Disconnect"}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.cardTitle}>Alpaca brokerage</Text>
          {alpaca?.connected ? (
            <View style={styles.pillOk}>
              <Text style={styles.pillOkText}>Connected</Text>
            </View>
          ) : (
            <View style={styles.pillMuted}>
              <Text style={styles.pillMutedText}>Not connected</Text>
            </View>
          )}
        </View>
        {alpaca?.connected ? (
          <>
            <Text style={styles.mutedText}>
              {alpaca.alpaca_account_id ? `Account: ${alpaca.alpaca_account_id}` : "Account linked"}
              {alpaca.last_sync_at ? ` • Last sync ${String(alpaca.last_sync_at).slice(0, 19).replace("T", " ")}` : ""}
            </Text>
            <View style={styles.btnRow}>
              <Pressable style={styles.secondaryBtn} onPress={syncAlpaca} disabled={alpacaBusy}>
                <Text style={styles.secondaryBtnText}>{alpacaBusy ? "Syncing…" : "Sync now"}</Text>
              </Pressable>
              <Pressable style={styles.dangerBtn} onPress={unlinkAlpaca} disabled={alpacaBusy}>
                <Text style={styles.dangerBtnText}>{alpacaBusy ? "Unlinking…" : "Unlink"}</Text>
              </Pressable>
            </View>
          </>
        ) : (
          <>
            <Text style={styles.mutedText}>Link Alpaca to enable portfolio sync in mobile.</Text>
            <TextInput
              style={styles.input}
              value={alpacaApiKeyId}
              onChangeText={setAlpacaApiKeyId}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Alpaca API Key ID"
              placeholderTextColor="#94a3b8"
            />
            <TextInput
              style={styles.input}
              value={alpacaApiKeySecret}
              onChangeText={setAlpacaApiKeySecret}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
              placeholder="Alpaca API Key Secret"
              placeholderTextColor="#94a3b8"
            />
            <View style={styles.switchRow}>
              <Text style={styles.switchLabel}>Paper trading account</Text>
              <Switch value={alpacaPaper} onValueChange={setAlpacaPaper} />
            </View>
            <Pressable
              style={[styles.primaryBtn, (!alpacaApiKeyId.trim() || !alpacaApiKeySecret.trim() || alpacaBusy) && { opacity: 0.6 }]}
              onPress={connectAlpaca}
              disabled={!alpacaApiKeyId.trim() || !alpacaApiKeySecret.trim() || alpacaBusy}
            >
              <Text style={styles.primaryBtnText}>{alpacaBusy ? "Linking…" : "Link Alpaca"}</Text>
            </Pressable>
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, padding: 20, backgroundColor: "#fff", gap: 12 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 24, fontWeight: "900" },
  card: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, backgroundColor: "#fff", gap: 12 },
  cardHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  cardTitle: { fontSize: 16, fontWeight: "900", color: "#0f172a" },
  primaryBtn: { backgroundColor: "#135bec", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  primaryBtnText: { color: "#fff", fontWeight: "900" },
  secondaryBtn: { backgroundColor: "#eff6ff", borderWidth: 1, borderColor: "#bfdbfe", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  secondaryBtnText: { color: "#1d4ed8", fontWeight: "800" },
  dangerBtn: { backgroundColor: "#fff1f2", borderWidth: 1, borderColor: "#fecdd3", paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12 },
  dangerBtnText: { color: "#be123c", fontWeight: "800" },
  subText: { color: "#475569", fontSize: 12, fontWeight: "900" },
  list: { gap: 10 },
  listRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 14, padding: 12, gap: 8 },
  listName: { fontSize: 14, fontWeight: "900", color: "#0f172a", flex: 1, marginRight: 10 },
  listMeta: { fontSize: 12, color: "#64748b", fontWeight: "700" },
  mutedText: { color: "#64748b" },
  infoText: { color: "#0369a1", fontWeight: "700" },
  errorText: { color: "#dc2626" },
  pillOk: { backgroundColor: "#dcfce7", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  pillOkText: { color: "#166534", fontWeight: "800", fontSize: 12 },
  pillMuted: { backgroundColor: "#f1f5f9", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  pillMutedText: { color: "#334155", fontWeight: "800", fontSize: 12 },
  btnRow: { flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" },
  input: {
    borderWidth: 1,
    borderColor: "#cbd5e1",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "#0f172a",
    backgroundColor: "#fff",
  },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  switchLabel: { color: "#334155", fontWeight: "700" },
});

