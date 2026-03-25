import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { InvestmentsOverviewBody } from "../../src/screens/InvestmentsOverviewBody";
import { theme } from "../../src/theme";

export default function InvestmentsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={[styles.root, { paddingTop: insets.top }]}>
      <View style={styles.stackHeader}>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>Back</Text>
        </Pressable>
        <Text style={styles.title}>Investments</Text>
        <View style={{ width: 56 }} />
      </View>
      <InvestmentsOverviewBody stackMode />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: theme.colors.background },
  stackHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.xl,
    paddingBottom: 4,
    backgroundColor: theme.colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.outlineVariant,
  },
  back: { color: theme.colors.primary, fontFamily: "Inter_700Bold", fontSize: 16 },
  title: { fontSize: 16, fontFamily: "Inter_800ExtraBold", color: theme.colors.onSurface },
});
