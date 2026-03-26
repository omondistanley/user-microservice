import React, { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { authClient } from "../../src/authClient";
import { gatewayJson, gatewayUrl } from "../../src/gatewayRequest";
import { formatApiDetail } from "../../src/formatApiDetail";
import { theme } from "../../src/theme";
import { Button } from "../../src/components/ui/Button";

type ImportRow = {
  row_number: number;
  validation_error?: string | null;
  is_duplicate?: boolean;
  normalized_payload?: { date?: string; amount?: unknown; description?: string } | null;
};

type JobPayload = {
  job_id: string;
  status?: string;
  filename?: string;
  rows?: ImportRow[];
};

export default function ExpenseImportScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobPayload | null>(null);
  const [pickedName, setPickedName] = useState<string | null>(null);

  const pickAndUpload = async () => {
    setError(null);
    const resPick = await DocumentPicker.getDocumentAsync({
      type: ["text/csv", "text/comma-separated-values", "application/vnd.ms-excel"],
      copyToCacheDirectory: true,
    });
    if (resPick.canceled || !resPick.assets?.[0]) return;
    const asset = resPick.assets[0];
    if (!asset.uri) {
      setError("Could not read file.");
      return;
    }
    const name = (asset.name || "import.csv").toLowerCase();
    if (!name.endsWith(".csv")) {
      setError("Please choose a .csv file.");
      return;
    }
    setPickedName(asset.name ?? "import.csv");
    setBusy(true);
    setJob(null);
    try {
      const form = new FormData();
      form.append("file", {
        uri: asset.uri,
        name: asset.name ?? "import.csv",
        type: asset.mimeType ?? "text/csv",
      } as unknown as Blob);
      const url = `${gatewayUrl("/api/v1/expenses/import")}?dry_run=true&preset=generic`;
      const up = await authClient.requestWithRefresh(url, { method: "POST", body: form });
      const body = await up.json().catch(() => null);
      if (!up.ok) {
        throw new Error(formatApiDetail((body as { detail?: unknown })?.detail, "Upload failed."));
      }
      const jobId = String((body as { job_id?: string })?.job_id ?? "");
      if (!jobId) throw new Error("No job_id returned.");
      const full = await gatewayJson<JobPayload>(`/api/v1/expenses/import/${encodeURIComponent(jobId)}`, {
        method: "GET",
      });
      setJob(full);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  const refreshJob = async () => {
    if (!job?.job_id) return;
    setError(null);
    setBusy(true);
    try {
      const full = await gatewayJson<JobPayload>(`/api/v1/expenses/import/${encodeURIComponent(job.job_id)}`, {
        method: "GET",
      });
      setJob(full);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  };

  const commit = async () => {
    if (!job?.job_id) return;
    const invalid = job.rows?.filter((r) => r.validation_error).length ?? 0;
    if (invalid > 0) {
      setError("Fix invalid rows in the CSV, then upload again. Duplicate rows are skipped on commit.");
      return;
    }
    setCommitting(true);
    setError(null);
    try {
      const counts = await gatewayJson<Record<string, unknown>>(
        `/api/v1/expenses/import/${encodeURIComponent(job.job_id)}/commit`,
        { method: "POST" },
      );
      const inserted = (counts as { inserted_rows?: number })?.inserted_rows;
      setError(null);
      setJob(null);
      setPickedName(null);
      const msg =
        typeof inserted === "number"
          ? `Imported ${inserted} expense(s).`
          : `Commit done: ${JSON.stringify(counts)}`;
      Alert.alert("Import", msg, [{ text: "OK", onPress: () => router.replace("/expenses") }]);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Commit failed.");
    } finally {
      setCommitting(false);
    }
  };

  const insertableCount = job?.rows?.filter((r) => !r.validation_error && !r.is_duplicate).length ?? 0;
  const dupCount = job?.rows?.filter((r) => r.is_duplicate && !r.validation_error).length ?? 0;
  const invalidCount = job?.rows?.filter((r) => r.validation_error).length ?? 0;

  return (
    <View style={[styles.root, { paddingTop: insets.top, backgroundColor: theme.colors.background }]}>
      <View style={styles.header}>
        <Pressable hitSlop={12} onPress={() => router.back()}>
          <MaterialCommunityIcons name="arrow-left" size={24} color={theme.colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Import CSV</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 32 }}>
        <Text style={styles.body}>
          Same flow as web: upload validates rows (dry run), review, then commit. Preset: generic columns.
        </Text>
        <Button title={pickedName ? `Replace file (${pickedName})` : "Choose CSV"} onPress={pickAndUpload} loading={busy} disabled={busy} />
        <View style={{ height: 10 }} />
        {job ? (
          <Button title="Refresh preview" tone="secondary" onPress={refreshJob} loading={busy} disabled={busy} />
        ) : null}

        {error ? <Text style={styles.err}>{error}</Text> : null}

        {busy && !job ? <ActivityIndicator style={{ marginTop: 16 }} color={theme.colors.primary} /> : null}

        {job ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Job {job.job_id.slice(0, 8)}…</Text>
            <Text style={styles.meta}>{job.filename ?? ""}</Text>
            <Text style={styles.meta}>Status: {job.status ?? "—"}</Text>
            <Text style={[styles.meta, { marginTop: 8 }]}>
              Insertable: {insertableCount} · Duplicates (skipped): {dupCount} · Invalid: {invalidCount}
            </Text>
            <Button
              title="Commit import"
              onPress={commit}
              loading={committing}
              disabled={committing || invalidCount > 0 || !(job.rows?.length ?? 0)}
            />
            <Text style={[styles.disclaimer, { marginTop: 10 }]}>
              Commit runs only when every row passes validation. Duplicate rows are omitted from insertion.
            </Text>

            <Text style={styles.previewK}>Preview (first 12 rows)</Text>
            {(job.rows ?? []).slice(0, 12).map((r) => (
              <View key={r.row_number} style={styles.rowLine}>
                <Text style={styles.rowNum}>#{r.row_number}</Text>
                <View style={{ flex: 1 }}>
                  {r.validation_error ? (
                    <Text style={styles.rowErr}>{r.validation_error}</Text>
                  ) : r.is_duplicate ? (
                    <Text style={styles.rowWarn}>Possible duplicate</Text>
                  ) : (
                    <Text style={styles.rowOk}>
                      {r.normalized_payload?.date ?? "—"} · {String(r.normalized_payload?.amount ?? "—")}{" "}
                      {r.normalized_payload?.description
                        ? `· ${String(r.normalized_payload.description).slice(0, 40)}`
                        : ""}
                    </Text>
                  )}
                </View>
              </View>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: theme.colors.outlineVariant,
  },
  title: { fontSize: 17, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
  body: { fontSize: 13, color: theme.colors.onSurfaceVariant, lineHeight: 20, marginBottom: 14 },
  card: {
    marginTop: 16,
    padding: 14,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    gap: 8,
  },
  cardTitle: { fontFamily: "Inter_800ExtraBold", fontSize: 16, color: theme.colors.onSurface },
  meta: { fontSize: 12, color: theme.colors.secondary },
  disclaimer: { fontSize: 11, color: theme.colors.secondary },
  previewK: {
    marginTop: 12,
    fontSize: 11,
    fontFamily: "Inter_800ExtraBold",
    textTransform: "uppercase",
    color: theme.colors.onSurfaceVariant,
  },
  rowLine: { flexDirection: "row", gap: 8, marginTop: 8, alignItems: "flex-start" },
  rowNum: { fontSize: 11, fontFamily: "Inter_700Bold", color: theme.colors.secondary, width: 36 },
  rowOk: { fontSize: 12, color: theme.colors.onSurface },
  rowErr: { fontSize: 12, color: theme.colors.error },
  rowWarn: { fontSize: 12, color: "#b45309" },
  err: { color: theme.colors.error, marginTop: 12, fontFamily: "Inter_600SemiBold" },
});
