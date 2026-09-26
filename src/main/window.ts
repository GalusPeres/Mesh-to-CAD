import { BrowserWindow, app, nativeTheme } from 'electron';

import type { Settings } from '@shared/settings';
import { TITLE_BAR_COLORS, type ThemeName } from '@shared/theme';

import { preloadPath } from './paths';

export function resolvedTheme(settings: Settings): ThemeName {
  if (settings.theme === 'system') return nativeTheme.shouldUseDarkColors ? 'dark' : 'light';
  return settings.theme;
}

/** Frameless window with native caption buttons drawn over the 32 px title bar. */
export function createMainWindow(settings: Settings, url: string): BrowserWindow {
  const colors = TITLE_BAR_COLORS[resolvedTheme(settings)];
  const window = new BrowserWindow({
    width: 1600,
    height: 960,
    minWidth: 1280,
    minHeight: 720,
    show: false,
    title: 'Mesh-to-CAD',
    titleBarStyle: 'hidden',
    titleBarOverlay: { ...colors, height: 32 },
    backgroundColor: colors.color,
    webPreferences: {
      preload: preloadPath(),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
      spellcheck: false,
      devTools: !app.isPackaged,
    },
  });
  window.once('ready-to-show', () => window.show());
  void window.loadURL(url);
  return window;
}
