import React from "react";
import { StyleSheet, TextInput, TextInputProps, View } from "react-native";
import { AppTheme, useAppTheme } from "../../theme";

type Props = TextInputProps & {
  left?: React.ReactNode;
};

export function Input({ left, style, ...rest }: Props) {
  const theme = useAppTheme();
  const styles = createStyles(theme);
  return (
    <View style={styles.wrap}>
      {left ? <View style={styles.left}>{left}</View> : null}
      <TextInput
        {...rest}
        placeholderTextColor={theme.colors.onSurfaceVariant}
        style={[styles.input, left ? styles.inputWithLeft : null, style]}
      />
    </View>
  );
}

const createStyles = (theme: AppTheme) => StyleSheet.create({
  wrap: {
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.surface,
    minHeight: 48,
    justifyContent: "center",
  },
  left: {
    position: "absolute",
    left: 12,
    zIndex: 2,
  },
  input: {
    color: theme.colors.onSurface,
    paddingVertical: 12,
    paddingHorizontal: 12,
    fontFamily: "Inter_400Regular",
  },
  inputWithLeft: {
    paddingLeft: 42,
  },
});
