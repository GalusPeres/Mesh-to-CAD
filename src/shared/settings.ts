// Application preferences, stored by the main process in %APPDATA%\Mesh-to-CAD\settings.json.
// Project-specific values (tolerance, snap units) live in the document instead.

import type { JsonValue } from './protocol/wireTypes';

export type Language = 'de' | 'en';
export type ThemeSetting = 'system' | 'dark' | 'light';

export interface Settings {
  language: Language;
  theme: ThemeSetting;
  navigation: {
    invertWheel: boolean;
  };
  selection: {
    /** Clear the triangles a fit used once the fit is committed. */
    clearAfterFit: boolean;
  };
  /** Local control by automation clients such as the MCP server (docs/AUTOMATION.md). */
  automation: {
    enabled: boolean;
  };
  /** Per-tool preferences (brush size, collapsed sections, ...), keyed by tool id. */
  tools: Record<string, JsonValue>;
}

export type SettingsPatch = Partial<{
  language: Language;
  theme: ThemeSetting;
  navigation: Partial<Settings['navigation']>;
  selection: Partial<Settings['selection']>;
  automation: Partial<Settings['automation']>;
  tools: Record<string, JsonValue>;
}>;

export const DEFAULT_SETTINGS: Settings = {
  language: 'de',
  theme: 'system',
  navigation: { invertWheel: false },
  selection: { clearAfterFit: true },
  automation: { enabled: false },
  tools: {},
};

const LANGUAGES: readonly Language[] = ['de', 'en'];
const THEMES: readonly ThemeSetting[] = ['system', 'dark', 'light'];

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function flag(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

/** Settings from untrusted input (a file or IPC); invalid values fall back to defaults. */
export function validateSettings(input: unknown): Settings {
  const data = record(input);
  const navigation = record(data.navigation);
  const selection = record(data.selection);
  const automation = record(data.automation);
  const tools = record(data.tools) as Record<string, JsonValue>;
  return {
    language: oneOf(data.language, LANGUAGES, DEFAULT_SETTINGS.language),
    theme: oneOf(data.theme, THEMES, DEFAULT_SETTINGS.theme),
    navigation: {
      invertWheel: flag(navigation.invertWheel, DEFAULT_SETTINGS.navigation.invertWheel),
    },
    selection: {
      clearAfterFit: flag(selection.clearAfterFit, DEFAULT_SETTINGS.selection.clearAfterFit),
    },
    automation: {
      enabled: flag(automation.enabled, DEFAULT_SETTINGS.automation.enabled),
    },
    tools,
  };
}

export function applySettingsPatch(current: Settings, patch: SettingsPatch): Settings {
  return validateSettings({
    ...current,
    ...patch,
    navigation: { ...current.navigation, ...patch.navigation },
    selection: { ...current.selection, ...patch.selection },
    automation: { ...current.automation, ...patch.automation },
    tools: { ...current.tools, ...patch.tools },
  });
}
