import React, { useMemo, useState, useCallback } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { getAccessToken } from "../../src/authTokens";

type IncomeKind = "salary" | "gift" | "freelance" | "other";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function mapKindToPayload(kind: IncomeKind): { income_type: string; source_label?: string } {
  switch (kind) {
    case "salary":
      return { income_type: "salary" };
    case "gift":
      return { income_type: "other", source_label: "Gift" };
    case "freelance":
      return { income_type: "freelance" };
    default:
      return { income_type: "other" };
  }
}

const KEYPAD: (string | "bs")[][] = [
  ["1", "2", "3"],
  ["4", "5", "6"],
  ["7", "8", "9"],
  [".", "0", "bs"],
];

const MAX_CENTS = 999_999_999; // $9,999,999.99

export default function AddIncomeScreen() {
  const router = useRouter();
  const [cents, setCents] = useState(0);
  const [kind, setKind] = useState<IncomeKind>("salary");
  const [note, setNote] = useState("");
  const [initial, setInitial] = useState("•");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    let c = true;
    (async () => {
      const t = await getAccessToken();
      if (!c || !t) return;
      try {
        const res = await fetch(`${GATEWAY_BASE_URL}/user/me`, {
          headers: { Authorization: `Bearer ${t}` },
        });
        const data = await res.json().catch(() => null);
        if (data?.first_name) setInitial(String(data.first_name).charAt(0).toUpperCase());
        else if (data?.email) setInitial(String(data.email).charAt(0).toUpperCase());
      } catch {
        /* ignore */
      }
    })();
    return () => {
      c = false;
    };
  }, []);

  const displayAmount = useMemo(() => (cents / 100).toFixed(2), [cents]);
  const amountNumber = useMemo(() => cents / 100, [cents]);

  const onKey = useCallback((k: string) => {
    setError(null);
    if (k === "bs") {
      setCents((c) => Math.floor(c / 10));
      return;
    }
    if (k === ".") return;
    if (!/^\d$/.test(k)) return;
    const d = Number(k);
    setCents((c) => Math.min(c * 10 + d, MAX_CENTS));
  }, []);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (!amountNumber || amountNumber <= 0) throw new Error("Enter a transaction amount.");
      const { income_type, source_label } = mapKindToPayload(kind);
      const payload: Record<string, unknown> = {
        amount: amountNumber,
        date: todayISO(),
        currency: "USD",
        income_type,
      };
      if (source_label) payload.source_label = source_label;
      if (note.trim()) payload.description = note.trim().slice(0, 2000);

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/income`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(data?.detail ? String(data.detail) : "Failed to create income.");
      router.back();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  const CategoryTile = ({
    k,
    labelSmall,
    labelBig,
    icon,
    tileBg,
    iconColor,
  }: {
    k: IncomeKind;
    labelSmall: string;
    labelBig: string;
    icon: keyof typeof MaterialCommunityIcons.glyphMap;
    tileBg: string;
    iconColor: string;
  }) => {
    const selected = kind === k;
    return (
      <Pressable
        onPress={() => setKind(k)}
        style={[
          styles.catTile,
          selected ? styles.catTileOn : styles.catTileOff,
        ]}
      >
        <View style={[styles.catIconWrap, { backgroundColor: tileBg }]}>
          <MaterialCommunityIcons name={icon} size={22} color={iconColor} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.catSmall}>{labelSmall}</Text>
          <Text style={styles.catBig}>{labelBig}</Text>
        </View>
      </Pressable>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Add Income</Text>
        <View style={styles.headerAvatar}>
          <Text style={styles.headerAvatarTxt}>{initial}</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.amountCard}>
          <Text style={styles.amountKicker}>TRANSACTION AMOUNT</Text>
          <View style={styles.amountRow}>
            <Text style={styles.dollar}>$</Text>
            <Text style={styles.amountFig}>{displayAmount}</Text>
          </View>
        </View>

        <View style={styles.catGrid}>
          <CategoryTile
            k="salary"
            labelSmall="ACTIVE"
            labelBig="Salary"
            icon="cash-multiple"
            tileBg={`${theme.colors.primary}18`}
            iconColor={theme.colors.primary}
          />
          <CategoryTile
            k="gift"
            labelSmall="ONE-TIME"
            labelBig="Gift"
            tileBg={theme.colors.tertiaryContainer}
            iconColor={theme.colors.tertiary}
            icon="gift-outline"
          />
          <CategoryTile
            k="freelance"
            labelSmall="PASSIVE"
            labelBig="Side Hustle"
            tileBg={theme.colors.secondaryContainer}
            iconColor={theme.colors.secondary}
            icon="briefcase-outline"
          />
          <CategoryTile
            k="other"
            labelSmall="CUSTOM"
            labelBig="Others"
            tileBg={theme.colors.surfaceContainerHigh}
            iconColor={theme.colors.onSurfaceVariant}
            icon="plus-circle-outline"
          />
        </View>

        <View style={styles.noteWrap}>
          <MaterialCommunityIcons
            name="note-text-outline"
            size={20}
            color={theme.colors.onSurfaceVariant}
            style={styles.noteIcon}
          />
          <TextInput
            value={note}
            onChangeText={setNote}
            placeholder="Add a note (e.g. Q3 Bonus)"
            placeholderTextColor={theme.colors.onSurfaceVariant}
            style={styles.noteInput}
          />
        </View>

        <Pressable
          style={({ pressed }) => [styles.saveBtn, pressed && { opacity: 0.92 }]}
          onPress={onSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator color={theme.colors.onPrimary} />
          ) : (
            <>
              <Text style={styles.saveBtnTxt}>Save Transaction</Text>
              <MaterialCommunityIcons name="arrow-right" size={22} color={theme.colors.onPrimary} />
            </>
          )}
        </Pressable>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <View style={styles.keypadCard}>
          {KEYPAD.map((row, ri) => (
            <View key={String(ri)} style={styles.keypadRow}>
              {row.map((cell) => (
                <Pressable
                  key={cell}
                  style={({ pressed }) => [styles.keyBtn, pressed && styles.keyBtnPressed]}
                  onPress={() => onKey(cell === "bs" ? "bs" : cell)}
                >
                  {cell === "bs" ? (
                    <MaterialCommunityIcons name="backspace-outline" size={24} color={theme.colors.onSurface} />
                  ) : (
                    <Text style={styles.keyTxt}>{cell}</Text>
                  )}
                </Pressable>
              ))}
            </View>
          ))}
        </View>

        <View style={styles.infoBanner}>
          <MaterialCommunityIcons name="information" size={22} color={theme.colors.primary} />
          <Text style={styles.infoTxt}>
            Income transactions are automatically reflected in cashflow summaries and budget projections tied to this
            month.
          </Text>
        </View>
        <View style={{ height: 24 }} />
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
    paddingHorizontal: theme.spacing.xl,
    paddingVertical: theme.spacing.md,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.outlineVariant,
    ...theme.shadows.sm,
  },
  headerTitle: {
    fontSize: 18,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurface,
  },
  headerAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.secondaryFixed,
    alignItems: "center",
    justifyContent: "center",
  },
  headerAvatarTxt: { fontFamily: "Inter_800ExtraBold", color: theme.colors.primary },
  scroll: {
    padding: theme.spacing.xl,
    paddingTop: theme.spacing.lg,
    gap: theme.spacing.lg,
  },
  amountCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 24,
    padding: theme.spacing.xxl,
    borderWidth: 1,
    borderColor: `${theme.colors.outlineVariant}80`,
  },
  amountKicker: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.secondary,
    letterSpacing: 2,
    marginBottom: theme.spacing.sm,
  },
  amountRow: { flexDirection: "row", alignItems: "baseline", gap: 4 },
  dollar: {
    fontSize: 36,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.primary,
  },
  amountFig: {
    fontSize: 44,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: -1,
    flex: 1,
  },
  catGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  catTile: {
    width: "47%",
    flexGrow: 1,
    borderRadius: 16,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  catTileOn: {
    backgroundColor: theme.colors.surface,
    borderWidth: 2,
    borderColor: theme.colors.primary,
  },
  catTileOff: {
    backgroundColor: theme.colors.surfaceContainerLow,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  catIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  catSmall: {
    fontSize: 10,
    fontFamily: "Inter_700Bold",
    color: theme.colors.secondary,
    letterSpacing: 1,
  },
  catBig: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  noteWrap: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    paddingLeft: 14,
  },
  noteIcon: { marginRight: 8 },
  noteInput: {
    flex: 1,
    paddingVertical: 16,
    paddingRight: 14,
    fontSize: 14,
    fontFamily: "Inter_500Medium",
    color: theme.colors.onSurface,
  },
  saveBtn: {
    backgroundColor: theme.colors.primary,
    borderRadius: 18,
    paddingVertical: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    ...theme.shadows.md,
  },
  saveBtnTxt: {
    color: theme.colors.onPrimary,
    fontSize: 17,
    fontFamily: "Inter_700Bold",
  },
  errorText: { color: theme.colors.error, fontFamily: "Inter_600SemiBold", textAlign: "center" },
  keypadCard: {
    backgroundColor: theme.colors.surface,
    borderRadius: 24,
    padding: 18,
    borderWidth: 1,
    borderColor: `${theme.colors.outlineVariant}80`,
    gap: 10,
    ...theme.shadows.sm,
  },
  keypadRow: { flexDirection: "row", gap: 10 },
  keyBtn: {
    flex: 1,
    height: 56,
    borderRadius: 16,
    backgroundColor: theme.colors.surfaceContainerLow,
    alignItems: "center",
    justifyContent: "center",
  },
  keyBtnPressed: { backgroundColor: theme.colors.surfaceVariant },
  keyTxt: { fontSize: 22, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  infoBanner: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 12,
    backgroundColor: theme.colors.primaryContainer,
    borderRadius: 16,
    padding: 18,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}18`,
  },
  infoTxt: {
    flex: 1,
    fontSize: 13,
    fontFamily: "Inter_500Medium",
    color: theme.colors.onPrimaryContainer,
    lineHeight: 20,
  },
});
