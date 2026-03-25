import { Text, View, StyleSheet } from "react-native";

export default function MoreScreen() {
  return (
    <View style={styles.box}>
      <Text style={styles.body}>
        Placeholder for settings, integrations, and profile — mirror the web “More” journey and gateway routes.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flex: 1, padding: 24 },
  body: { fontSize: 15, color: "#334155", lineHeight: 22 },
});
