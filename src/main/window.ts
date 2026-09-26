import { BrowserWindow, app, nativeTheme, screen } from 'electron';

import type { Settings } from '@shared/settings';
import { TITLE_BAR_COLORS, type ThemeName } from '@shared/theme';

import { preloadPath } from './paths';

export function resolvedTheme(settings: Settings): ThemeName {
  if (settings.theme === 'system') return nativeTheme.shouldUseDarkColors ? 'dark' : 'light';
  return settings.theme;
}

const PREFERRED_SIZE = { width: 1600, height: 960 };
const MIN_SIZE = { width: 960, height: 600 };

/** Frameless window with native caption buttons drawn over the 32 px title bar. */
export function createMainWindow(settings: Settings, url: string): BrowserWindow {
  const colors = TITLE_BAR_COLORS[resolvedTheme(settings)];
  // Laptops at 150 % scaling offer about 1280 x 670 logical pixels; the window must fit.
  const workArea = screen.getPrimaryDisplay().workAreaSize;
  const window = new BrowserWindow({
    width: Math.min(PREFERRED_SIZE.width, workArea.width),
    height: Math.min(PREFERRED_SIZE.height, workArea.height),
    minWidth: Math.min(MIN_SIZE.width, workArea.width),
    minHeight: Math.min(MIN_SIZE.height, workArea.height),
    center: true,
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
