import React from "react";
import { SafeAreaView, ScrollView, StyleSheet, View, ViewProps } from "react-native";
import { theme } from "../../theme";

type Props = ViewProps & {
  scroll?: boolean;
  padded?: boolean;
};

export function Screen({ scroll = true, padded = true, style, children, ...rest }: Props) {
  const content = (
    <View style={[styles.content, padded ? styles.padded : null, style]} {...rest}>
      {children}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      {scroll ? <ScrollView contentContainerStyle={styles.scrollContainer}>{content}</ScrollView> : content}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  scrollContainer: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    gap: 12,
  },
  padded: {
    padding: 20,
  },
});
