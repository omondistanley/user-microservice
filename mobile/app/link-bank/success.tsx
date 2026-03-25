import React, { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as SecureStore from "expo-secure-store";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";

const PLAID_LINK_TOKEN_KEY = "pocketii_plaid_link_token";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function LinkBankSuccessScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"loading" | "polling" | "exchanging" | "syncing" | "done">("loading");
  const [foundPublicTokens, setFoundPublicTokens] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setPhase("loading");
      setError(null);
      try {
        const linkToken = await SecureStore.getItemAsync(PLAID_LINK_TOKEN_KEY);
        if (cancelled) return;
        if (!linkToken) {
          throw new Error("No Plaid link session found. Start linking again.");
        }

        // Poll until Plaid has produced public tokens.
        setPhase("polling");
        const startedAt = Date.now();
        const timeoutMs = 2 * 60 * 1000; // 2 minutes
        let publicTokens: string[] = [];
        while (Date.now() - startedAt < timeoutMs) {
          const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/link-token/get`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ link_token: linkToken }),
          });
          const json = await res.json().catch(() => null);
          if (!res.ok) {
            throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to query Plaid link status.");
          }
          const pts: unknown = (json as any)?.public_tokens;
          publicTokens = Array.isArray(pts) ? (pts as string[]) : [];
          if (cancelled) return;
          if (publicTokens.length > 0) break;
          await sleep(2000);
        }

        if (!publicTokens.length) {
          throw new Error("Plaid did not provide public tokens in time. You can retry from Integrations.");
        }
        setFoundPublicTokens(publicTokens);

        // Exchange tokens for items (server stores access token + item_id).
        setPhase("exchanging");
        for (const pt of publicTokens) {
          const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/item`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ public_token: pt }),
          });
          const json = await res.json().catch(() => null);
          if (!res.ok) {
            throw new Error((json as any)?.detail ? String((json as any).detail) : "Failed to exchange Plaid public token.");
          }
        }

        // Import transactions into expenses.
        setPhase("syncing");
        const syncRes = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/plaid/sync`, {
          method: "POST",
        });
        const syncJson = await syncRes.json().catch(() => null);
        if (!syncRes.ok) {
          throw new Error((syncJson as any)?.detail ? String((syncJson as any).detail) : "Failed to sync plaid transactions.");
        }

        // Clear link_token now that we're done.
        await SecureStore.deleteItemAsync(PLAID_LINK_TOKEN_KEY);
        if (cancelled) return;
        setPhase("done");
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ? String(e.message) : "Bank linking failed.");
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <SafeAreaView style={[styles.safe, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Bank Linked</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.container, { paddingBottom: insets.bottom + 24 }]}>
        {phase === "done" && !error ? (
          <>
            <View style={styles.successRing}>
              <View style={styles.successInner}>
                <MaterialCommunityIcons name="check" size={40} color={theme.colors.onPrimary} />
              </View>
            </View>
            <Text style={styles.successTitle}>Success!</Text>
            <Text style={styles.successSub}>Your bank account has been linked to PocketII.</Text>

            <View style={styles.bankCard}>
              <View style={styles.bankIcon}>
                <MaterialCommunityIcons name="bank" size={28} color={theme.colors.onPrimary} />
              </View>
              <Text style={styles.bankName}>Connected institution</Text>
              <Text style={styles.bankStatus}>Status: Active</Text>
            </View>

            <Text style={styles.importHead}>Accounts imported</Text>
            <Text style={styles.importHint}>Balances and transactions will appear as sync completes.</Text>

            <Pressable
              style={styles.primaryBtn}
              onPress={() => router.replace("/(tabs)/")}
            >
              <Text style={styles.primaryBtnText}>Continue to dashboard</Text>
              <MaterialCommunityIcons name="arrow-right" size={22} color={theme.colors.onPrimary} />
            </Pressable>
            <Text style={styles.footerNote}>Manage accounts anytime from Settings → Integrations.</Text>
          </>
        ) : (
          <>
            <Text style={styles.title}>Finishing…</Text>
            <Text style={styles.subtitle}>
              {phase === "polling"
                ? "Waiting for Plaid"
                : phase === "exchanging"
                  ? "Securing your link"
                  : phase === "syncing"
                    ? "Importing transactions"
                    : "Starting"}
            </Text>
            {error ? <Text style={styles.errorText}>{error}</Text> : <ActivityIndicator style={{ marginTop: 20 }} color={theme.colors.primary} />}
            {foundPublicTokens.length ? (
              <View style={styles.tokensBox}>
                <Text style={styles.tokensTitle}>Tokens received</Text>
                <Text style={styles.tokenText}>{foundPublicTokens.length} connection(s)</Text>
              </View>
            ) : null}
            <Pressable style={styles.secondaryBtn} onPress={() => router.replace("/settings/integrations")}>
              <Text style={styles.secondaryBtnText}>Back to Integrations</Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.surfaceDim },
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
  container: { flexGrow: 1, paddingHorizontal: theme.spacing.xl, paddingTop: 24, alignItems: "center" },
  successRing: {
    width: 96,
    height: 96,
    borderRadius: 999,
    backgroundColor: theme.colors.primaryContainer,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
  },
  successInner: {
    width: 64,
    height: 64,
    borderRadius: 999,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  successTitle: { fontSize: 28, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  successSub: {
    textAlign: "center",
    marginTop: 10,
    fontSize: 15,
    color: theme.colors.secondary,
    fontFamily: "Inter_400Regular",
    lineHeight: 22,
    paddingHorizontal: 12,
  },
  bankCard: {
    marginTop: 28,
    width: "100%",
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.xl,
    padding: theme.spacing.xl,
    alignItems: "center",
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
  },
  bankIcon: {
    width: 56,
    height: 56,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 12,
  },
  bankName: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  bankStatus: { marginTop: 4, fontSize: 13, color: theme.colors.secondary },
  importHead: { marginTop: 28, alignSelf: "flex-start", fontSize: 16, fontFamily: "Inter_800ExtraBold" },
  importHint: { alignSelf: "flex-start", marginTop: 6, fontSize: 13, color: theme.colors.secondary },
  primaryBtn: {
    marginTop: 24,
    width: "100%",
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    ...theme.shadows.md,
  },
  primaryBtnText: { color: theme.colors.onPrimary, fontFamily: "Inter_800ExtraBold", fontSize: 16 },
  footerNote: { marginTop: 12, fontSize: 12, color: theme.colors.secondary, textAlign: "center" },
  title: { fontSize: 22, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface, alignSelf: "flex-start" },
  subtitle: { fontSize: 14, color: theme.colors.secondary, alignSelf: "flex-start", marginTop: 8 },
  errorText: { color: theme.colors.error, marginTop: 14, fontSize: 14, fontFamily: "Inter_600SemiBold" },
  tokensBox: { marginTop: 14, borderWidth: 1, borderColor: theme.colors.outlineVariant, borderRadius: 16, padding: 14, width: "100%" },
  tokensTitle: { fontSize: 12, color: theme.colors.secondary, fontFamily: "Inter_700Bold" },
  tokenText: { fontSize: 12, color: theme.colors.onSurface, fontFamily: "Inter_600SemiBold", marginTop: 6 },
  secondaryBtn: {
    marginTop: 18,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    alignSelf: "stretch",
    alignItems: "center",
  },
  secondaryBtnText: { color: theme.colors.onSurface, fontFamily: "Inter_700Bold" },
});

