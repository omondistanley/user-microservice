import React from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { useRouter } from "expo-router";
import { Screen } from "../../src/components/ui/Screen";
import { Text } from "../../src/components/ui/Text";
import { Card } from "../../src/components/ui/Card";
import { theme } from "../../src/theme";

export default function MoreScreen() {
  const router = useRouter();

  const Item = ({ title, href }: { title: string; href: string }) => (
    <Pressable style={({ pressed }) => [styles.item, pressed && styles.itemPressed]} onPress={() => router.push(href)}>
      <Text style={styles.itemText}>{title}</Text>
      <Text style={styles.itemArrow}>›</Text>
    </Pressable>
  );

  return (
    <Screen>
      <Text variant="headline" style={styles.title}>
        More
      </Text>

      <Card variant="container">
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Money
        </Text>
        <Item title="Goals" href="/goals" />
        <Item title="Expenses" href="/expenses" />
        <Item title="Income" href="/income" />
        <Item title="Recurring" href="/recurring" />
        <Item title="Net Worth" href="/net-worth" />
        <Item title="Import expenses (CSV)" href="/expenses/import" />
      </Card>

      <Card variant="container">
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Insights
        </Text>
        <Item title="Analytics" href="/analytics" />
        <Item title="Insights" href="/insights" />
        <Item title="Reports" href="/reports" />
      </Card>

      <Card variant="container">
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Investing
        </Text>
        <Item title="Investments" href="/investments" />
        <Item title="Recommendations" href="/recommendations" />
        <Item title="Watchlist" href="/watchlist" />
        <Item title="Teller (EU banks)" href="/teller" />
      </Card>

      <Card variant="container">
        <Text variant="label" uppercase color={theme.colors.onSurfaceVariant}>
          Account
        </Text>
        <Item title="Settings" href="/settings" />
        <Item title="Integrations" href="/settings/integrations" />
        <Item title="Security" href="/security" />
        <Item title="Notifications" href="/notifications" />
        <Item title="Household" href="/household" />
        <Item title="Sessions" href="/sessions" />
        <Item title="Saved Views" href="/saved-views" />
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: { marginBottom: 2 },
  item: {
    backgroundColor: theme.colors.surface,
    borderRadius: 0,
    paddingVertical: 13,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  itemPressed: { backgroundColor: theme.colors.surfaceContainer },
  itemText: { fontSize: 13, fontFamily: "Inter_600SemiBold", color: theme.colors.onSurface },
  itemArrow: { fontSize: 18, color: theme.colors.outlineVariant, fontWeight: "300" },
});
