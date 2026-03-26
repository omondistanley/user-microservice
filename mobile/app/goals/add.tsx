import React, { useState } from "react";
import { ActivityIndicator, Button, SafeAreaView, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { formatApiDetail } from "../../src/formatApiDetail";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export default function AddGoalScreen() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [targetAmount, setTargetAmount] = useState("");
  const [targetCurrency, setTargetCurrency] = useState("USD");
  const [targetDate, setTargetDate] = useState("");
  const [startAmount, setStartAmount] = useState("0");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const payload: any = {
        name: name.trim(),
        target_amount: Number(targetAmount),
        target_currency: targetCurrency.trim().toUpperCase().slice(0, 3) || "USD",
        start_amount: Number(startAmount || 0),
      };
      if (!payload.name) throw new Error("Goal name is required.");
      if (!Number.isFinite(payload.target_amount) || payload.target_amount < 0) throw new Error("Target amount must be valid.");
      if (!Number.isFinite(payload.start_amount) || payload.start_amount < 0) throw new Error("Starting amount must be valid.");
      if (targetDate.trim()) payload.target_date = targetDate.trim().slice(0, 10);

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/api/v1/goals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error(formatApiDetail(data?.detail, "Failed to create goal."));

      router.replace(`/goals/${encodeURIComponent(String(data.goal_id))}`);
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Failed to create goal.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "#fff" }}>
      <View style={styles.container}>
        <Text style={styles.title}>New Goal</Text>

        <Text style={styles.label}>Goal name</Text>
        <TextInput value={name} onChangeText={setName} style={styles.input} placeholder="e.g. Emergency fund" />

        <Text style={styles.label}>Target amount</Text>
        <TextInput
          value={targetAmount}
          onChangeText={setTargetAmount}
          style={styles.input}
          keyboardType="decimal-pad"
          placeholder="0.00"
        />

        <Text style={styles.label}>Currency</Text>
        <TextInput value={targetCurrency} onChangeText={setTargetCurrency} style={styles.input} placeholder="USD" />

        <Text style={styles.label}>Target date (optional)</Text>
        <TextInput
          value={targetDate}
          onChangeText={setTargetDate}
          style={styles.input}
          placeholder={toISODate(new Date())}
        />

        <Text style={styles.label}>Starting amount</Text>
        <TextInput
          value={startAmount}
          onChangeText={setStartAmount}
          style={styles.input}
          keyboardType="decimal-pad"
          placeholder="0.00"
        />

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <View style={{ marginTop: 12 }}>
          {saving ? <ActivityIndicator /> : <Button title="Create goal" onPress={onSave} />}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, gap: 10 },
  title: { fontSize: 24, fontWeight: "900" },
  label: { fontSize: 12, fontWeight: "900", color: "#334155" },
  input: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: "#fff",
  },
  errorText: { color: "#dc2626" },
});

