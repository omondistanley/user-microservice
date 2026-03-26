import React, { useMemo, useState } from "react";
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
import { formatApiDetail } from "../../src/formatApiDetail";
import { theme } from "../../src/theme";

type RecurrenceRule = "weekly" | "monthly" | "yearly";

const CATEGORIES: { label: string; code: number }[] = [
  { label: "Entertainment", code: 5 },
  { label: "Bills & Utilities", code: 4 },
  { label: "Food & Dining", code: 1 },
  { label: "Health & Fitness", code: 6 },
  { label: "Transport", code: 2 },
];

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function AddRecurringScreen() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryIndex, setCategoryIndex] = useState<number | null>(null);
  const [startDate, setStartDate] = useState(todayISO());
  const [recurrenceRule, setRecurrenceRule] = useState<RecurrenceRule>("monthly");
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [freqOpen, setFreqOpen] = useState(false);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const amountNumber = useMemo(() => {
    const n = Number(amount);
    return Number.isFinite(n) ? n : null;
  }, [amount]);

  const catLabel =
    categoryIndex !== null ? CATEGORIES[categoryIndex]?.label ?? "Select a category" : "Select a category";

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      if (!name.trim()) throw new Error("Transaction name is required.");
      if (amountNumber === null || amountNumber < 0) throw new Error("Amount must be a valid number.");
      if (categoryIndex === null) throw new Error("Select a category.");
      const cat = CATEGORIES[categoryIndex];
      if (!cat) throw new Error("Invalid category.");

      const payload = {
        amount: amountNumber,
        currency: "USD",
        category_code: cat.code,
        description: name.trim().slice(0, 2000),
        recurrence_rule: recurrenceRule,
        next_due_date: startDate.slice(0, 10),
      };

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/recurring-expenses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(formatApiDetail(data?.detail, "Failed to create recurring."));
      router.back();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()} style={styles.backHit}>
          <MaterialCommunityIcons name="chevron-left" size={28} color={theme.colors.secondary} />
        </Pressable>
        <Text style={styles.headerTitle}>New Recurring</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.main} keyboardShouldPersistTaps="handled">
        <View style={styles.block}>
          <Text style={styles.lbl}>Transaction Name</Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder="e.g. Netflix Subscription"
            placeholderTextColor={theme.colors.onSurfaceVariant}
            style={styles.input}
          />

          <Text style={[styles.lbl, styles.lblPad]}>Amount</Text>
          <View style={styles.moneyRow}>
            <Text style={styles.dollarSign}>$</Text>
            <TextInput
              value={amount}
              onChangeText={setAmount}
              placeholder="0.00"
              placeholderTextColor={theme.colors.onSurfaceVariant}
              keyboardType="decimal-pad"
              style={[styles.input, styles.moneyInput]}
            />
          </View>

          <Text style={[styles.lbl, styles.lblPad]}>Category</Text>
          <Pressable style={styles.selectOuter} onPress={() => setCategoryOpen((o) => !o)}>
            <Text style={[styles.selectTxt, categoryIndex === null && styles.ph]}>
              {catLabel}
            </Text>
            <MaterialCommunityIcons name="chevron-down" size={22} color={theme.colors.secondary} />
          </Pressable>
          {categoryOpen ? (
            <View style={styles.pickList}>
              {CATEGORIES.map((c, i) => (
                <Pressable
                  key={c.code}
                  style={styles.pickRow}
                  onPress={() => {
                    setCategoryIndex(i);
                    setCategoryOpen(false);
                  }}
                >
                  <Text style={styles.pickRowTxt}>{c.label}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>

        <Text style={styles.schedTitle}>SCHEDULE</Text>
        <View style={styles.row2}>
          <View style={{ flex: 1 }}>
            <Text style={styles.lbl}>Start Date</Text>
            <View style={styles.dateRow}>
              <TextInput
                value={startDate}
                onChangeText={setStartDate}
                placeholder="YYYY-MM-DD"
                placeholderTextColor={theme.colors.onSurfaceVariant}
                style={styles.dateInput}
              />
              <MaterialCommunityIcons name="calendar-outline" size={22} color={theme.colors.secondary} />
            </View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.lbl}>Frequency</Text>
            <Pressable style={styles.selectOuter} onPress={() => setFreqOpen((o) => !o)}>
              <Text style={styles.selectTxt}>
                {recurrenceRule === "weekly" ? "Weekly" : recurrenceRule === "yearly" ? "Yearly" : "Monthly"}
              </Text>
              <MaterialCommunityIcons name="chevron-down" size={22} color={theme.colors.secondary} />
            </Pressable>
            {freqOpen ? (
              <View style={[styles.pickList, styles.pickAbs]}>
                {(
                  [
                    ["weekly", "Weekly"],
                    ["monthly", "Monthly"],
                    ["yearly", "Yearly"],
                  ] as const
                ).map(([v, label]) => (
                  <Pressable
                    key={v}
                    style={styles.pickRow}
                    onPress={() => {
                      setRecurrenceRule(v);
                      setFreqOpen(false);
                    }}
                  >
                    <Text style={styles.pickRowTxt}>{label}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
          </View>
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <Pressable
          style={({ pressed }) => [styles.primaryBtn, pressed && { opacity: 0.95 }]}
          onPress={onSave}
          disabled={saving}
        >
          {saving ? (
            <ActivityIndicator color={theme.colors.onPrimary} />
          ) : (
            <Text style={styles.primaryBtnTxt}>Create Recurring Payment</Text>
          )}
        </Pressable>

        <Pressable onPress={() => router.back()} style={styles.cancelBtn}>
          <Text style={styles.cancelTxt}>Cancel</Text>
        </Pressable>
        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const R = 8;

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.surfaceContainerLow },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.surfaceContainerLow,
    backgroundColor: theme.colors.surface,
  },
  backHit: { padding: 4, marginLeft: -8 },
  headerTitle: { fontSize: 18, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
  main: { padding: 20, paddingTop: 8, backgroundColor: theme.colors.surfaceContainerLow },
  block: { gap: 0 },
  lbl: { fontSize: 14, fontFamily: "Inter_600SemiBold", color: theme.colors.onSecondaryFixedVariant, marginBottom: 6 },
  lblPad: { marginTop: 18 },
  input: {
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: R,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
    backgroundColor: theme.colors.surface,
  },
  moneyRow: { position: "relative" },
  dollarSign: {
    position: "absolute",
    left: 14,
    top: 15,
    zIndex: 1,
    fontSize: 16,
    color: theme.colors.secondary,
    fontFamily: "Inter_500Medium",
  },
  moneyInput: { paddingLeft: 28 },
  schedTitle: {
    fontSize: 13,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurfaceVariant,
    letterSpacing: 1.2,
    marginTop: 28,
    marginBottom: 14,
  },
  row2: { flexDirection: "row", gap: 14, zIndex: 2 },
  dateRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: R,
    paddingRight: 12,
    backgroundColor: theme.colors.surface,
  },
  dateInput: {
    flex: 1,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
    fontFamily: "Inter_400Regular",
    color: theme.colors.onSurface,
  },
  selectOuter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: R,
    paddingHorizontal: 14,
    paddingVertical: 14,
    backgroundColor: theme.colors.surface,
  },
  selectTxt: { fontSize: 16, fontFamily: "Inter_400Regular", color: theme.colors.onSurface, flex: 1 },
  ph: { color: theme.colors.onSurfaceVariant },
  pickList: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: R,
    backgroundColor: theme.colors.surface,
    overflow: "hidden",
  },
  pickAbs: {},
  pickRow: { paddingVertical: 14, paddingHorizontal: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.outlineVariant },
  pickRowTxt: { fontSize: 15, fontFamily: "Inter_500Medium", color: theme.colors.onSurface },
  primaryBtn: {
    marginTop: 32,
    backgroundColor: theme.colors.primary,
    borderRadius: R,
    paddingVertical: 17,
    alignItems: "center",
    ...theme.shadows.md,
  },
  primaryBtnTxt: { color: theme.colors.onPrimary, fontSize: 16, fontFamily: "Inter_700Bold" },
  cancelBtn: { marginTop: 14, alignItems: "center", paddingVertical: 12 },
  cancelTxt: { fontSize: 14, fontFamily: "Inter_500Medium", color: theme.colors.secondary },
  errorText: { color: theme.colors.error, marginTop: 12, fontFamily: "Inter_600SemiBold" },
});
