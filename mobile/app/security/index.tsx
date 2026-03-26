import React, { useState } from "react";
import { View } from "react-native";
import { useRouter } from "expo-router";
import { GATEWAY_BASE_URL } from "../../src/config";
import { authClient } from "../../src/authClient";
import { clearTokens } from "../../src/authTokens";
import { Screen } from "../../src/components/ui/Screen";
import { TopBar } from "../../src/components/ui/TopBar";
import { Card } from "../../src/components/ui/Card";
import { Text } from "../../src/components/ui/Text";
import { Input } from "../../src/components/ui/Input";
import { Button } from "../../src/components/ui/Button";
import { theme } from "../../src/theme";
import { formatApiDetail } from "../../src/formatApiDetail";

export default function SecurityScreen() {
  const router = useRouter();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const changePassword = async () => {
    setSubmitting(true);
    setError(null);
    setSuccess(null);
    try {
      if (!currentPassword) throw new Error("Current password is required.");
      if (!newPassword || newPassword.length < 8) throw new Error("New password must be at least 8 characters.");

      const res = await authClient.requestWithRefresh(`${GATEWAY_BASE_URL}/user/me/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });

      if (!res.ok) {
        const json = await res.json().catch(() => null);
        throw new Error(formatApiDetail(json?.detail, "Failed to change password."));
      }

      setSuccess("Password changed. You have been signed out on other devices.");
      // Tokens may still be valid on this device; we can optionally keep the user signed in.
      setCurrentPassword("");
      setNewPassword("");
    } catch (e: any) {
      setError(e?.message ? String(e.message) : "Change password failed.");
    } finally {
      setSubmitting(false);
    }
  };

  const signOut = async () => {
    await clearTokens();
    router.replace("/login");
  };

  return (
    <Screen>
      <TopBar title="Security" onBack={() => router.back()} />

        <Card>
          <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
            Change password
          </Text>
          <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
            Current password
          </Text>
          <Input
            value={currentPassword}
            onChangeText={setCurrentPassword}
            secureTextEntry
            placeholder="••••••••"
            autoCapitalize="none"
          />

          <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
            New password
          </Text>
          <Input
            value={newPassword}
            onChangeText={setNewPassword}
            secureTextEntry
            placeholder="New password (min 8 chars)"
            autoCapitalize="none"
          />

          {error ? <Text color={theme.colors.error}>{error}</Text> : null}
          {success ? <Text color="#16a34a">{success}</Text> : null}

          <View style={{ marginTop: 12 }}>
            <Button title="Update password" onPress={changePassword} loading={submitting} disabled={submitting} />
          </View>
        </Card>

        <Card variant="container">
          <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
            Session
          </Text>
          <Text color={theme.colors.onSurfaceVariant}>Manage devices or sign out completely.</Text>
          <View style={{ marginTop: 10 }}>
            <Button title="Sessions" tone="secondary" onPress={() => router.push("/sessions")} />
            <View style={{ height: 10 }} />
            <Button title="Sign out" tone="danger" onPress={signOut} />
          </View>
        </Card>
    </Screen>
  );
}


