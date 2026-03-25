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
    <Pressable style={styles.item} onPress={() => router.push(href)}>
      <Text style={styles.itemText}>{title}</Text>
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
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  itemText: { fontSize: 14, fontFamily: "Inter_700Bold", color: theme.colors.onSurface },
});
