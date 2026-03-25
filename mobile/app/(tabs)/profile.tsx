import React from "react";
import { StyleSheet, View } from "react-native";
import WebAppView from "../../src/WebAppView";

export default function ProfileScreen() {
  return (
    <View style={styles.container}>
      <WebAppView path="/profile" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});

