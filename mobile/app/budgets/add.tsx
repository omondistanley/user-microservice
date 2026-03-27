import React, { useMemo, useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { formatApiDetail } from "../../src/formatApiDetail";
import { theme } from "../../src/theme";

const CATEGORIES = [
  { code: 1, label: "Food" },
  { code: 2, label: "Transportation" },
  { code: 3, label: "Travel" },
  { code: 4, label: "Utilities" },
  { code: 5, label: "Entertainment" },
  { code: 6, label: "Health" },
  { code: 7, label: "Shopping" },
  { code: 8, label: "Other" },
] as const;

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function lastDayOfMonthISO(d: Date): string {
  return toISODate(new Date(d.getFullYear(), d.getMonth() + 1, 0));
}

export default function AddBudgetScreen() {
  const router = useRouter();
  const today = useMemo(() => new Date(), []);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [categoryCode, setCategoryCode] = useState<number | null>(null);
  const [startDate, setStartDate] = useState(toISODate(today));
  const [endDate, setEndDate] = useState(lastDayOfMonthISO(today));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const parsedAmount = Number(String(amount).replace(/,/g, ""));
      if (!Number.isFinite(parsedAmount) || parsedAmount < 0) {
        throw new Error("Enter a valid budget amount.");
      }
      if (!categoryCode) {
        throw new Error("Select a category.");
      }
      if (!startDate.trim()) {
        throw new Error("Start date is required.");
      }

      const payload: Record<string, unknown> = {
        amount: parsedAmount,
        category_code: categoryCode,
        start_date: startDate.trim().slice(0, 10),
        alert_thresholds: [80, 100],
        alert_channel: "in_app",
      };
      if (name.trim()) payload.name = name.trim();
      if (endDate.trim()) payload.end_date = endDate.trim().slice(0, 10);

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/budgets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(formatApiDetail(data?.detail, "Failed to create budget."));
      }

      router.replace("/(tabs)/budgets");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to create budget.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Screen>
      <View style={styles.headerRow}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text variant="headline" style={styles.title}>
          Add Budget
        </Text>
        <View style={{ width: 24 }} />
      </View>

      <View style={styles.heroCard} testID="e2e-budget-add-screen">
        <Text variant="label" uppercase color={theme.colors.primary}>
          First Budget
        </Text>
        <Text style={styles.heroTitle}>Create a category limit for this month.</Text>
        <Text style={styles.heroSub}>
          Mobile now supports first-time budget creation directly, without sending you back to another flow.
        </Text>
      </View>

      <View style={styles.formCard}>
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Name
        </Text>
        <Input value={name} onChangeText={setName} placeholder="e.g. Monthly Food" />

        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Amount
        </Text>
        <Input
          testID="e2e-budget-amount"
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="0.00"
        />

        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Category
        </Text>
        <View style={styles.categoryGrid}>
          {CATEGORIES.map((category) => {
            const selected = categoryCode === category.code;
            return (
              <Pressable
                key={category.code}
                style={[styles.categoryChip, selected && styles.categoryChipSelected]}
                onPress={() => setCategoryCode(category.code)}
              >
                <Text
                  style={[
                    styles.categoryChipText,
                    selected && { color: theme.colors.onPrimary },
                  ]}
                >
                  {category.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Start Date
        </Text>
        <Input value={startDate} onChangeText={setStartDate} placeholder="YYYY-MM-DD" />

        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          End Date
        </Text>
        <Input value={endDate} onChangeText={setEndDate} placeholder="YYYY-MM-DD" />

        <View style={styles.helperCard}>
          <MaterialCommunityIcons name="bell-badge-outline" size={18} color={theme.colors.primary} />
          <Text style={styles.helperText}>
            New budgets default to in-app alerts at 80% and 100% of the limit.
          </Text>
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <Button
          title="Create Budget"
          onPress={onSave}
          loading={saving}
          disabled={saving}
          testID="e2e-budget-add-submit"
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    fontSize: 18,
  },
  heroCard: {
    padding: 16,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.primaryContainer,
    borderWidth: 1,
    borderColor: `${theme.colors.primary}22`,
    gap: 6,
  },
  heroTitle: {
    fontSize: 22,
    fontFamily: "Inter_800ExtraBold",
    color: theme.colors.onSurface,
  },
  heroSub: {
    color: theme.colors.onSurfaceVariant,
    fontFamily: "Inter_400Regular",
    lineHeight: 20,
  },
  formCard: {
    gap: 10,
    padding: 16,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  categoryGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  categoryChip: {
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 999,
    backgroundColor: theme.colors.surfaceContainer,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  categoryChipSelected: {
    backgroundColor: theme.colors.primary,
    borderColor: theme.colors.primary,
  },
  categoryChipText: {
    fontSize: 12,
    fontFamily: "Inter_700Bold",
    color: theme.colors.onSurface,
  },
  helperCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    padding: 12,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surfaceContainerLow,
  },
  helperText: {
    flex: 1,
    color: theme.colors.onSurfaceVariant,
    fontFamily: "Inter_500Medium",
    lineHeight: 18,
  },
  errorText: {
    color: theme.colors.error,
    fontFamily: "Inter_600SemiBold",
  },
});
