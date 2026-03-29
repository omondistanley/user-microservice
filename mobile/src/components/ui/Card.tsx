import React from "react";
import { StyleProp, StyleSheet, View, ViewStyle } from "react-native";
import { AppTheme, useAppTheme } from "../../theme";

type Variant = "surface" | "container";

type Props = {
  variant?: Variant;
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
};

export function Card({ variant = "surface", style, children }: Props) {
  const theme = useAppTheme();
  const styles = createStyles(theme);
  return <View style={[styles.base, variant === "container" ? styles.container : styles.surface, style]}>{children}</View>;
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  base: {
    borderRadius: theme.radii.lg,
    padding: 16,
    gap: 10,
  },
  surface: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  container: {
    backgroundColor: theme.colors.surfaceContainerLow,
  },
});
