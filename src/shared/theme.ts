// Title-bar colours the main process needs before the renderer has loaded.
// They must equal --bg-app and --text in src/renderer/styles/tokens.css
// (checked by src/renderer/styles/designRules.test.ts).

export type ThemeName = 'dark' | 'light';

export const TITLE_BAR_COLORS: Record<ThemeName, { color: string; symbolColor: string }> = {
  dark: { color: '#1C1D20', symbolColor: '#E4E5E7' },
  light: { color: '#E9EAEC', symbolColor: '#1C1D20' },
};
