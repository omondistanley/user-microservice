import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useColorScheme } from "react-native";
import * as SecureStore from "expo-secure-store";
import { GATEWAY_BASE_URL } from "../config";
import { getAccessToken } from "../authTokens";
import { darkColors, lightColors } from "./tokens/colors";
import { typography } from "./tokens/typography";

export type ThemeMode = "light" | "dark";
export type ThemePreference = ThemeMode | "system";

export const radii = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 9999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
} as const;

export const shadows = {
  sm: {
    shadowColor: "#135bec",
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  md: {
    shadowColor: "#135bec",
    shadowOpacity: 0.12,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 4,
  },
} as const;

type AppColors = { [K in keyof typeof lightColors]: string };

function createTheme(mode: ThemeMode) {
  const colors: AppColors = mode === "dark" ? { ...darkColors } : { ...lightColors };
  return {
    colors,
    typography,
    spacing,
    radii,
    shadows,
  } as const;
}

export type AppTheme = ReturnType<typeof createTheme>;

const THEME_PREFERENCE_KEY = "pocketii.theme_preference";
const VALID_PREFERENCES: ThemePreference[] = ["light", "dark", "system"];

export const theme: AppTheme = createTheme("light");

function isThemePreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && VALID_PREFERENCES.includes(value as ThemePreference);
}

function applyModeToTheme(mode: ThemeMode) {
  Object.assign(theme.colors, mode === "dark" ? darkColors : lightColors);
}

type ThemeContextValue = {
  theme: AppTheme;
  preference: ThemePreference;
  resolvedMode: ThemeMode;
  hydrated: boolean;
  setPreference: (preference: ThemePreference) => Promise<void>;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme,
  preference: "system",
  resolvedMode: "light",
  hydrated: false,
  setPreference: async () => {},
});

async function readStoredPreference(): Promise<ThemePreference | null> {
  try {
    const value = await SecureStore.getItemAsync(THEME_PREFERENCE_KEY);
    return isThemePreference(value) ? value : null;
  } catch {
    return null;
  }
}

async function writeStoredPreference(preference: ThemePreference): Promise<void> {
  try {
    await SecureStore.setItemAsync(THEME_PREFERENCE_KEY, preference);
  } catch {
    /* ignore local persistence errors */
  }
}

async function readRemotePreference(): Promise<ThemePreference | null> {
  try {
    const accessToken = await getAccessToken();
    if (!accessToken) return null;
    const res = await fetch(`${GATEWAY_BASE_URL}/api/v1/settings`, {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!res.ok) return null;
    const data = await res.json().catch(() => null);
    const value = data?.theme_preference;
    return isThemePreference(value) ? value : null;
  } catch {
    return null;
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [preference, setPreferenceState] = useState<ThemePreference>("system");
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      const localPreference = await readStoredPreference();
      if (active && localPreference) {
        setPreferenceState(localPreference);
      }
      const remotePreference = await readRemotePreference();
      if (active && remotePreference) {
        setPreferenceState(remotePreference);
        await writeStoredPreference(remotePreference);
      }
      if (active) setHydrated(true);
    })();
    return () => {
      active = false;
    };
  }, []);

  const resolvedMode: ThemeMode = preference === "system"
    ? (systemScheme === "dark" ? "dark" : "light")
    : preference;

  useEffect(() => {
    applyModeToTheme(resolvedMode);
  }, [resolvedMode]);

  const setPreference = useCallback(async (nextPreference: ThemePreference) => {
    setPreferenceState(nextPreference);
    await writeStoredPreference(nextPreference);
  }, []);

  const value = useMemo<ThemeContextValue>(() => ({
    theme: createTheme(resolvedMode),
    preference,
    resolvedMode,
    hydrated,
    setPreference,
  }), [hydrated, preference, resolvedMode, setPreference]);

  return React.createElement(ThemeContext.Provider, { value }, children);
}

export function useAppTheme(): AppTheme {
  return useContext(ThemeContext).theme;
}

export function useThemePreference() {
  const { preference, resolvedMode, hydrated, setPreference } = useContext(ThemeContext);
  return { preference, resolvedMode, hydrated, setPreference };
}
