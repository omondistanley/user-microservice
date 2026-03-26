import React, { useCallback, useMemo, useState } from "react";
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
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Location from "expo-location";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";

type TxKind = "expense" | "income";

type CatKey = "food" | "travel" | "bills" | "shopping" | "health" | "other";

const CAT_MAP: Record<CatKey, { code: number; label: string; icon: keyof typeof MaterialCommunityIcons.glyphMap }> = {
  food: { code: 1, label: "Food", icon: "silverware-fork-knife" },
  travel: { code: 3, label: "Travel", icon: "airplane" },
  bills: { code: 4, label: "Bills", icon: "receipt" },
  shopping: { code: 7, label: "Shopping", icon: "shopping" },
  health: { code: 6, label: "Health", icon: "heart-pulse" },
  other: { code: 8, label: "Other", icon: "dots-horizontal" },
};

const MAX_CENTS = 999_999_999;

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function fmtDateLong(iso: string): string {
  try {
    const d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

export default function AddExpenseScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ amount?: string; note?: string; kind?: string }>();

  const [kind, setKind] = useState<TxKind>(
    params.kind === "income" ? "income" : "expense",
  );
  const [cents, setCents] = useState(() => {
    const a = params.amount ? Number(params.amount) : 0;
    if (Number.isFinite(a) && a > 0) return Math.round(a * 100);
    return 0;
  });
  const [cat, setCat] = useState<CatKey>("food");
  const [date, setDate] = useState(todayISO());
  const [note, setNote] = useState(params.note ? String(params.note) : "");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const displayAmount = useMemo(() => (cents / 100).toFixed(2), [cents]);
  const amountNumber = cents / 100;

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

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      if (!amountNumber || amountNumber <= 0) throw new Error("Enter an amount.");
      if (!date) throw new Error("Date is required.");

      if (kind === "expense") {
        const c = CAT_MAP[cat];
        const payload: Record<string, unknown> = {
          amount: amountNumber,
          date: date.slice(0, 10),
          currency: "USD",
          category_code: c.code,
        };
        let locNote = "";
        try {
          const perm = await Location.requestForegroundPermissionsAsync();
          if (perm.status === "granted") {
            const pos = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });
            locNote = ` [loc ${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}]`;
          }
        } catch {
          /* optional */
        }
        const descCombined = `${note.trim()}${locNote}`.trim();
        if (descCombined) payload.description = descCombined.slice(0, 2000);

        const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/expenses`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error(formatApiDetail(data?.detail, "Failed to save expense."));
      } else {
        const payload: Record<string, unknown> = {
          amount: amountNumber,
          date: date.slice(0, 10),
          currency: "USD",
          income_type: "other",
        };
        if (note.trim()) payload.description = note.trim().slice(0, 2000);

        const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/income`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error(formatApiDetail(data?.detail, "Failed to save income."));
      }

      router.back();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.topBar}>
        <Pressable hitSlop={12} onPress={() => router.back()} style={styles.iconBtn}>
          <MaterialCommunityIcons name="close" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Add Transaction</Text>
        <Pressable hitSlop={12} onPress={save} disabled={saving} style={styles.iconBtn}>
          {saving ? (
            <ActivityIndicator size="small" color={theme.colors.primary} />
          ) : (
            <MaterialCommunityIcons name="check" size={24} color={theme.colors.primary} />
          )}
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.amountBlock}>
          <Text style={styles.amountLabel}>Amount</Text>
          <View style={styles.amountRow}>
            <Text style={styles.dollarLight}>$</Text>
            <Text style={styles.amountHuge}>{displayAmount}</Text>
          </View>
        </View>

        <View style={styles.segment}>
          <Pressable
            style={[styles.segBtn, kind === "expense" && styles.segBtnOn]}
            onPress={() => setKind("expense")}
          >
            <Text style={[styles.segTxt, kind === "expense" && styles.segTxtOn]}>Expense</Text>
          </Pressable>
          <Pressable
            style={[styles.segBtn, kind === "income" && styles.segBtnOn]}
            onPress={() => setKind("income")}
          >
            <Text style={[styles.segTxt, kind === "income" && styles.segTxtOn]}>Income</Text>
          </Pressable>
        </View>

        <View>
          <View style={styles.dateRow}>
            <View style={styles.dateLeft}>
              <MaterialCommunityIcons name="calendar" size={22} color={theme.colors.primary} />
              <Text style={styles.dateDisplayMain}>{fmtDateLong(date)}</Text>
            </View>
            <MaterialCommunityIcons name="chevron-right" size={22} color={theme.colors.secondary} />
          </View>
          <TextInput
            value={date}
            onChangeText={setDate}
            placeholder="YYYY-MM-DD (edit date)"
            placeholderTextColor={theme.colors.secondary}
            style={styles.dateIsoInput}
          />
        </View>

        {kind === "expense" ? (
          <>
            <Text style={styles.catHeader}>Category</Text>
            <View style={styles.grid}>
              {(Object.keys(CAT_MAP) as CatKey[]).map((k) => {
                const meta = CAT_MAP[k];
                const on = cat === k;
                return (
                  <Pressable
                    key={k}
                    onPress={() => setCat(k)}
                    style={[styles.tile, on ? styles.tileOn : styles.tileOff]}
                  >
                    <MaterialCommunityIcons
                      name={meta.icon}
                      size={28}
                      color={on ? theme.colors.primary : theme.colors.secondary}
                    />
                    <Text style={styles.tileLabel}>{meta.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </>
        ) : (
          <Text style={styles.incomeHint}>
            Income is recorded as &ldquo;other&rdquo; with your note as the description.
          </Text>
        )}

        <TextInput
          value={note}
          onChangeText={setNote}
          placeholder="Add a note (optional)"
          placeholderTextColor={theme.colors.secondary}
          style={styles.noteInput}
        />

        <View style={styles.keypad}>
          {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
            <Pressable key={d} style={styles.key} onPress={() => onKey(d)}>
              <Text style={styles.keyText}>{d}</Text>
            </Pressable>
          ))}
          <Pressable style={styles.key} onPress={() => onKey(".")}>
            <Text style={styles.keyText}>.</Text>
          </Pressable>
          <Pressable style={styles.key} onPress={() => onKey("0")}>
            <Text style={styles.keyText}>0</Text>
          </Pressable>
          <Pressable style={styles.key} onPress={() => onKey("bs")}>
            <MaterialCommunityIcons name="backspace-outline" size={22} color={theme.colors.onSurface} />
          </Pressable>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable style={styles.saveBar} onPress={save} disabled={saving}>
          <MaterialCommunityIcons name="content-save-outline" size={22} color={theme.colors.onPrimary} />
          <Text style={styles.saveBarText}>Save Transaction</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.surface },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.md,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  iconBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: {
    flex: 1,
    textAlign: "center",
    fontSize: 17,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
  },
  scroll: { paddingBottom: 40 },
  amountBlock: { alignItems: "center", paddingVertical: 32, paddingHorizontal: 16 },
  amountLabel: {
    fontSize: 13,
    fontFamily: "Inter_600SemiBold",
    color: theme.colors.secondary,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    marginBottom: 8,
  },
  amountRow: { flexDirection: "row", alignItems: "baseline", gap: 4 },
  dollarLight: { fontSize: 36, fontFamily: "Inter_400Regular", color: theme.colors.secondary },
  amountHuge: {
    fontSize: 52,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: -1,
  },
  segment: {
    marginHorizontal: theme.spacing.xl,
    flexDirection: "row",
    backgroundColor: theme.colors.surfaceContainer,
    borderRadius: theme.radii.lg,
    padding: 4,
  },
  segBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: theme.radii.md,
    alignItems: "center",
  },
  segBtnOn: { backgroundColor: theme.colors.surface, ...theme.shadows.sm },
  segTxt: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.secondary },
  segTxtOn: { color: theme.colors.primary },
  dateRow: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 18,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: theme.radii.lg,
    padding: 14,
    backgroundColor: `${theme.colors.surfaceContainer}88`,
  },
  dateLeft: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  dateDisplayMain: { flex: 1, fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  dateIsoInput: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 8,
    fontSize: 12,
    fontFamily: "Inter_400Regular",
    color: theme.colors.secondary,
    paddingVertical: 6,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.outlineVariant,
  },
  catHeader: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 28,
    marginBottom: 12,
    fontSize: 13,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    paddingHorizontal: theme.spacing.xl,
    gap: 10,
  },
  tile: {
    width: "31%",
    minWidth: 100,
    flexGrow: 1,
    aspectRatio: 1,
    maxHeight: 110,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    padding: 8,
  },
  tileOn: {
    borderColor: theme.colors.primary,
    backgroundColor: `${theme.colors.primary}10`,
  },
  tileOff: {
    borderColor: theme.colors.outlineVariant,
    backgroundColor: theme.colors.surface,
  },
  tileLabel: { fontSize: 11, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  incomeHint: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 16,
    fontSize: 13,
    color: theme.colors.secondary,
    fontFamily: "Inter_400Regular",
    lineHeight: 18,
  },
  noteInput: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 24,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
    paddingVertical: 12,
    fontSize: 14,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
  },
  keypad: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginHorizontal: theme.spacing.lg,
                      marginTop: 20,
    gap: 10,
    justifyContent: "center",
  },
  key: {
    width: "28%",
    aspectRatio: 1.4,
    maxWidth: 110,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainer,
    alignItems: "center",
    justifyContent: "center",
  },
  keyText: { fontSize: 22, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  error: { color: theme.colors.error, marginHorizontal: theme.spacing.xl, marginTop: 12, fontFamily: "Inter_600SemiBold" },
  saveBar: {
    marginHorizontal: theme.spacing.xl,
    marginTop: 24,
    backgroundColor: theme.colors.primary,
    borderRadius: theme.radii.lg,
    paddingVertical: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    ...theme.shadows.md,
  },
  saveBarText: { color: theme.colors.onPrimary, fontSize: 16, fontFamily: "Inter_800ExtraBold" },
});
