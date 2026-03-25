import { Text, View, StyleSheet } from "react-native";
import { GATEWAY_BASE_URL } from "../../src/config";

export default function HomeScreen() {
  return (
    <View style={styles.box}>
      <Text style={styles.title}>pocketii</Text>
      <Text style={styles.muted}>
        Gateway: {GATEWAY_BASE_URL}. Sign-in with expo-auth-session + the same OAuth redirect strategy as web; store tokens with expo-secure-store.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flex: 1, padding: 24, justifyContent: "center" },
  title: { fontSize: 24, fontWeight: "700", marginBottom: 12 },
  muted: { fontSize: 14, color: "#64748b", lineHeight: 20 },
});
