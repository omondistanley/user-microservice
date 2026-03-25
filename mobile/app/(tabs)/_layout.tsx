import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Tabs } from "expo-router";
import { theme } from "../../src/theme";

type IconName = keyof typeof MaterialCommunityIcons.glyphMap;

function tabIcon(name: IconName) {
  return ({ color, focused }: { color: string; focused: boolean }) => (
    <MaterialCommunityIcons name={name} size={focused ? 26 : 24} color={color} />
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: true,
        headerStyle: { backgroundColor: theme.colors.surface },
        headerTintColor: theme.colors.onSurface,
        headerTitleStyle: { fontFamily: "Inter_700Bold", fontSize: 16 },
        tabBarStyle: {
          backgroundColor: theme.colors.surface,
          borderTopColor: theme.colors.outlineVariant,
          height: 62,
          paddingBottom: 6,
          paddingTop: 6,
        },
        tabBarActiveTintColor: theme.colors.primary,
        tabBarInactiveTintColor: theme.colors.onSurfaceVariant,
        tabBarLabelStyle: {
          fontSize: 9,
          fontFamily: "Inter_700Bold",
          letterSpacing: 0.6,
          textTransform: "uppercase",
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerShown: false,
          tabBarIcon: tabIcon("home"),
        }}
      />
      <Tabs.Screen
        name="transactions"
        options={{
          title: "Transactions",
          tabBarIcon: tabIcon("receipt-text-outline"),
        }}
      />
      <Tabs.Screen
        name="investments"
        options={{
          title: "Investments",
          headerShown: false,
          tabBarIcon: tabIcon("chart-line"),
        }}
      />
      <Tabs.Screen
        name="budgets"
        options={{
          title: "Budgets",
          headerShown: false,
          tabBarIcon: tabIcon("wallet-outline"),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          headerShown: false,
          tabBarIcon: tabIcon("account-outline"),
        }}
      />
    </Tabs>
  );
}
