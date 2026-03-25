import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";

type HouseholdItem = {
  household_id?: string;
  name?: string;
  role?: string;
  status?: string;
  created_at?: string;
};

type SettingsResponse = {
  active_household_id?: string | null;
};

type HouseholdMember = {
  household_id?: string;
  user_id?: number;
  role?: string;
  status?: string;
};

export default function HouseholdScreen() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [households, setHouseholds] = useState<HouseholdItem[]>([]);
  const [activeHouseholdId, setActiveHouseholdId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [selectedHouseholdId, setSelectedHouseholdId] = useState<string | null>(null);
  const [members, setMembers] = useState<HouseholdMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"viewer" | "editor">("viewer");
  const [inviting, setInviting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [hhJson, settingsJson] = await Promise.all([
        authClient.requestJsonWithRefresh<HouseholdItem[]>(`${GATEWAY_BASE_URL}/api/v1/households`, { method: "GET" }),
        authClient.requestJsonWithRefresh<SettingsResponse>(`${GATEWAY_BASE_URL}/api/v1/settings`, { method: "GET" }),
      ]);
      setHouseholds(Array.isArray(hhJson) ? hhJson : []);
      setActiveHouseholdId(settingsJson?.active_household_id ? String(settingsJson.active_household_id) : null);
      const firstId = settingsJson?.active_household_id
        ? String(settingsJson.active_household_id)
        : Array.isArray(hhJson) && hhJson.length && hhJson[0]?.household_id
          ? String(hhJson[0].household_id)
          : null;
      setSelectedHouseholdId(firstId);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load household.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedHousehold = useMemo(
    () => households.find((h) => String(h.household_id ?? "") === String(selectedHouseholdId ?? "")) ?? null,
    [households, selectedHouseholdId],
  );

  const loadMembers = async (householdId: string) => {
    setMembersLoading(true);
    try {
      const list = await authClient.requestJsonWithRefresh<HouseholdMember[]>(
        `${GATEWAY_BASE_URL}/api/v1/households/${encodeURIComponent(householdId)}/members`,
        { method: "GET" },
      );
      setMembers(Array.isArray(list) ? list : []);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to load members.");
      setMembers([]);
    } finally {
      setMembersLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedHouseholdId) {
      setMembers([]);
      return;
    }
    loadMembers(selectedHouseholdId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedHouseholdId]);

  const setActive = async (id: string | null) => {
    setSavingId(id);
    setError(null);
    try {
      const json = await authClient.requestJsonWithRefresh<any>(`${GATEWAY_BASE_URL}/api/v1/settings/active-household`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ household_id: id }),
      });
      // Response is UserSettingsResponse; active_household_id might be null.
      if (json && typeof json === "object") {
        const next = (json as any).active_household_id;
        setActiveHouseholdId(next ? String(next) : null);
      } else {
        setActiveHouseholdId(id);
      }
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to update household scope.");
    } finally {
      setSavingId(null);
    }
  };

  const inviteMember = async () => {
    if (!selectedHouseholdId) {
      setError("Select a household first.");
      return;
    }
    if (!inviteEmail.trim()) {
      setError("Enter an email to invite.");
      return;
    }
    setInviting(true);
    setError(null);
    try {
      await authClient.requestJsonWithRefresh(
        `${GATEWAY_BASE_URL}/api/v1/households/${encodeURIComponent(selectedHouseholdId)}/members`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
        },
      );
      setInviteEmail("");
      await loadMembers(selectedHouseholdId);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to invite member.");
    } finally {
      setInviting(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Household</Text>
        <View style={{ width: 60 }} />
      </View>

      {loading ? (
        <ActivityIndicator />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <>
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Scope</Text>
            <Pressable
              disabled={savingId !== null}
              onPress={() => setActive(null)}
              style={[styles.scopeBtn, activeHouseholdId === null ? styles.scopeBtnActive : null]}
            >
              <Text style={styles.scopeBtnText}>Personal (no household)</Text>
            </Pressable>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Your households</Text>
            {(households ?? []).map((h, idx) => {
              const id = h.household_id ? String(h.household_id) : String(idx);
              const isActive = activeHouseholdId === id;
              const isSelected = selectedHouseholdId === id;
              return (
                <Pressable
                  key={id}
                  style={[styles.row, isSelected ? styles.rowSelected : null]}
                  onPress={() => setSelectedHouseholdId(id)}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle} numberOfLines={1}>
                      {h.name ?? "Household"}
                    </Text>
                    <Text style={styles.rowMeta}>{h.role ? `Role: ${h.role}` : h.status ? `Status: ${h.status}` : ""}</Text>
                  </View>
                  <Pressable
                    disabled={savingId === id}
                    onPress={() => setActive(id)}
                    style={[styles.scopeBtn, isActive ? styles.scopeBtnActive : null, savingId === id ? styles.scopeBtnDisabled : null]}
                  >
                    <Text style={styles.scopeBtnText}>{isActive ? "Active" : savingId === id ? "Updating..." : "Set active"}</Text>
                  </Pressable>
                </Pressable>
              );
            })}
            {(households ?? []).length === 0 ? <Text style={styles.mutedText}>No households available.</Text> : null}
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>
              Members {selectedHousehold ? `· ${selectedHousehold.name ?? "Household"}` : ""}
            </Text>
            {membersLoading ? (
              <ActivityIndicator />
            ) : members.length ? (
              members.map((m, idx) => (
                <View key={`${String(m.user_id ?? idx)}`} style={styles.memberRow}>
                  <Text style={styles.rowTitle}>Member #{m.user_id ?? "—"}</Text>
                  <Text style={styles.rowMeta}>
                    {(m.role ?? "viewer").toUpperCase()} · {(m.status ?? "active").toUpperCase()}
                  </Text>
                </View>
              ))
            ) : (
              <Text style={styles.mutedText}>No members loaded.</Text>
            )}

            <View style={styles.inviteBlock}>
              <Text style={styles.sectionTitle}>Invite member</Text>
              <TextInput
                style={styles.input}
                value={inviteEmail}
                onChangeText={setInviteEmail}
                autoCapitalize="none"
                keyboardType="email-address"
                placeholder="name@email.com"
                placeholderTextColor="#94a3b8"
              />
              <View style={styles.roleRow}>
                <Pressable
                  style={[styles.roleBtn, inviteRole === "viewer" ? styles.scopeBtnActive : null]}
                  onPress={() => setInviteRole("viewer")}
                >
                  <Text style={styles.scopeBtnText}>Viewer</Text>
                </Pressable>
                <Pressable
                  style={[styles.roleBtn, inviteRole === "editor" ? styles.scopeBtnActive : null]}
                  onPress={() => setInviteRole("editor")}
                >
                  <Text style={styles.scopeBtnText}>Editor</Text>
                </Pressable>
              </View>
              <Pressable
                style={[styles.inviteBtn, inviting ? styles.scopeBtnDisabled : null]}
                onPress={inviteMember}
                disabled={inviting}
              >
                <Text style={styles.inviteBtnText}>{inviting ? "Inviting..." : "Invite Member"}</Text>
              </Pressable>
            </View>
          </View>
        </>
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
  card: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 16, padding: 16, gap: 10, backgroundColor: "#fff" },
  sectionTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a" },
  mutedText: { color: "#64748b", fontWeight: "900" },
  scopeBtn: { borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 14, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: "#fff", alignItems: "center" },
  scopeBtnActive: { borderColor: "#135bec", backgroundColor: "#dbeafe" },
  scopeBtnDisabled: { opacity: 0.7 },
  scopeBtnText: { fontWeight: "900", color: "#0f172a" },
  row: { flexDirection: "row", gap: 10, alignItems: "center", marginTop: 12 },
  rowSelected: { borderWidth: 1, borderColor: "#bfdbfe", borderRadius: 14, padding: 10, backgroundColor: "#f8fbff" },
  rowTitle: { fontSize: 14, fontWeight: "900", color: "#0f172a", flex: 1 },
  rowMeta: { fontSize: 12, fontWeight: "900", color: "#64748b", marginTop: 4 },
  memberRow: { marginTop: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#e2e8f0", paddingBottom: 10 },
  inviteBlock: { marginTop: 12, gap: 10 },
  input: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: "#0f172a",
  },
  roleRow: { flexDirection: "row", gap: 8 },
  roleBtn: { flex: 1, borderWidth: 1, borderColor: "#e2e8f0", borderRadius: 12, paddingVertical: 10, alignItems: "center" },
  inviteBtn: { backgroundColor: "#135bec", borderRadius: 12, paddingVertical: 12, alignItems: "center" },
  inviteBtnText: { color: "#fff", fontWeight: "900" },
});

