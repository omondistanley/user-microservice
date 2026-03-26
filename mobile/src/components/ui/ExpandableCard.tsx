import React from "react";
import { Pressable, StyleProp, StyleSheet, View, ViewStyle } from "react-native";
import { MaterialCommunityIcons } from "@expo/vector-icons";
import { theme } from "../../theme";

type Props = {
  expanded: boolean;
  onToggle: () => void;
  summary: React.ReactNode;
  children?: React.ReactNode;
  /** Card surface style (outer container). */
  style?: StyleProp<ViewStyle>;
  /**
   * When set, tapping the summary (not the chevron) runs this instead of toggling.
   * Chevron still expands/collapses — useful for “open detail” on row tap vs “edit” expand.
   */
  onSummaryPress?: () => void;
};

/**
 * Tap the header row to expand/collapse; expanded area holds details and actions (edit, delete).
 * With `onSummaryPress`, the main summary area triggers that callback; use the chevron to toggle.
 */
export function ExpandableCard({ expanded, onToggle, summary, children, style, onSummaryPress }: Props) {
  if (onSummaryPress) {
    return (
      <View style={[styles.card, style]}>
        <View style={styles.headerRow}>
          <Pressable
            onPress={onSummaryPress}
            style={({ pressed }) => [styles.summaryWrap, pressed && { opacity: 0.92 }]}
            accessibilityRole="button"
          >
            <View>{summary}</View>
          </Pressable>
          <Pressable
            onPress={onToggle}
            hitSlop={12}
            style={({ pressed }) => [styles.chevronBtn, pressed && { opacity: 0.92 }]}
            accessibilityRole="button"
            accessibilityLabel={expanded ? "Collapse" : "Expand"}
            accessibilityState={{ expanded }}
          >
            <MaterialCommunityIcons
              name={expanded ? "chevron-up" : "chevron-down"}
              size={22}
              color={theme.colors.onSurfaceVariant}
            />
          </Pressable>
        </View>
        {expanded && children ? <View style={styles.body}>{children}</View> : null}
      </View>
    );
  }

  return (
    <View style={[styles.card, style]}>
      <Pressable
        onPress={onToggle}
        style={({ pressed }) => [styles.headerRow, pressed && { opacity: 0.92 }]}
        accessibilityRole="button"
        accessibilityState={{ expanded }}
      >
        <View style={styles.summaryWrap}>{summary}</View>
        <MaterialCommunityIcons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={22}
          color={theme.colors.onSurfaceVariant}
        />
      </Pressable>
      {expanded && children ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    borderWidth: 1,
    borderColor: theme.colors.outlineVariant,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  summaryWrap: {
    flex: 1,
    minWidth: 0,
  },
  chevronBtn: {
    paddingVertical: 4,
    justifyContent: "center",
  },
  body: {
    marginTop: 14,
    paddingTop: 14,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: theme.colors.outlineVariant,
    gap: 12,
  },
});
