import React from "react";
import { StyleSheet, View } from "react-native";
import WebAppView from "../../src/WebAppView";

export default function MoreScreen() {
  return (
    <View style={styles.container}>
      <WebAppView path="/settings/integrations" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});
