import React from "react";
import { ActivityIndicator, Pressable, StyleSheet } from "react-native";
import { AppTheme, useAppTheme } from "../../theme";
import { Text } from "./Text";

type Tone = "primary" | "secondary" | "danger";

type Props = {
  title: string;
  onPress?: () => void;
  loading?: boolean;
  disabled?: boolean;
  tone?: Tone;
  testID?: string;
};

export function Button({ title, onPress, loading, disabled, tone = "primary", testID }: Props) {
  const theme = useAppTheme();
  const styles = createStyles(theme);
  const style =
    tone === "secondary"
      ? styles.secondary
      : tone === "danger"
        ? styles.danger
        : styles.primary;

  return (
    <Pressable
      testID={testID}
      style={[styles.base, style, disabled ? styles.disabled : null]}
      onPress={onPress}
      disabled={disabled || loading}
    >
      {loading ? (
        <ActivityIndicator color={tone === "primary" ? theme.colors.onPrimary : theme.colors.onSurface} />
      ) : (
        <Text
          variant="label"
          uppercase
          color={tone === "primary" ? theme.colors.onPrimary : theme.colors.onSurface}
          style={styles.text}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  base: {
    borderRadius: theme.radii.md,
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
  },
  primary: {
    backgroundColor: theme.colors.primary,
  },
  secondary: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
  },
  danger: {
    backgroundColor: theme.colors.errorContainer,
    borderWidth: 1,
    borderColor: "#fca5a5",
  },
  disabled: {
    opacity: 0.6,
  },
  text: {
    letterSpacing: 1.2,
  },
});
