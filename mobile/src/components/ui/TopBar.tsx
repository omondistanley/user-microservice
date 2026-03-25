import React from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Text } from "./Text";
import { theme } from "../../theme";

type Props = {
  title: string;
  onBack?: () => void;
  right?: React.ReactNode;
};

export function TopBar({ title, onBack, right }: Props) {
  return (
    <View style={styles.row}>
      <View style={styles.side}>
        {onBack ? (
          <Pressable onPress={onBack}>
            <Text variant="label" color={theme.colors.primary}>
              Back
            </Text>
          </Pressable>
        ) : null}
      </View>

      <Text variant="headline" style={styles.title}>
        {title}
      </Text>

      <View style={[styles.side, styles.right]}>{right}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  side: {
    width: 72,
  },
  right: {
    alignItems: "flex-end",
  },
  title: {
    flex: 1,
    textAlign: "center",
    fontSize: 22,
    lineHeight: 28,
  },
});
