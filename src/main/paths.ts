import { tmpdir } from 'node:os';
import path from 'node:path';

import { app } from 'electron';

/** True when started by the end-to-end tests (`M2C_E2E=1`). */
export const testMode = process.env.M2C_E2E === '1';

/**
 * `M2C_WINDOW=offscreen` (development only): the window opens far outside the
 * screen, without focus or taskbar button, and keeps rendering, so automation and
 * screenshots (`M2C_AUTOMATION=1`) can drive the app while someone uses the PC. It
 * keeps its settings, sessions and logs in a profile of its own, so automated runs
 * never touch the user's recent files or the unsaved work offered for recovery.
 */
export const offscreenMode = process.env.M2C_WINDOW === 'offscreen' && !app.isPackaged;

/**
 * `M2C_WINDOW=demo` (development only): a normal window, shown without taking the
 * focus, in the same separate profile, so automation can show the user something in
 * the running app without touching their own settings or unsaved work.
 */
export const demoMode = process.env.M2C_WINDOW === 'demo' && !app.isPackaged;

/** The window is driven by automation and keeps its data in a profile of its own. */
export const automationWindow = offscreenMode || demoMode;

/** Folder name of the profile in %APPDATA% and %LOCALAPPDATA%. */
export const PROFILE = automationWindow ? 'Mesh-to-CAD-automation' : 'Mesh-to-CAD';

/** Repository root in development; unused when packaged. */
export function repositoryRoot(): string {
  return path.resolve(__dirname, '..', '..');
}

/** Built renderer files (`dist/renderer`), next to the main bundle in `dist/main`. */
export function rendererDirectory(): string {
  return path.resolve(__dirname, '..', 'renderer');
}

export function preloadPath(): string {
  return path.resolve(__dirname, '..', 'preload', 'index.cjs');
}

/** Bundled resources (help pages, examples): `resources/` in the repository or the install folder. */
export function resourcesDirectory(): string {
  return app.isPackaged ? process.resourcesPath : path.join(repositoryRoot(), 'resources');
}

/** Per-machine data: sessions and logs (`%LOCALAPPDATA%\Mesh-to-CAD`). */
export function localDataDirectory(): string {
  if (testMode) return path.join(tmpdir(), 'mesh-to-cad-e2e', String(process.pid));
  const base = process.env.LOCALAPPDATA ?? app.getPath('userData');
  return path.join(base, PROFILE);
}

export function sessionsDirectory(): string {
  return path.join(localDataDirectory(), 'sessions');
}

export function logDirectory(): string {
  return path.join(localDataDirectory(), 'logs');
}

/** Roaming preferences (`%APPDATA%\Mesh-to-CAD\settings.json`). */
export function settingsPath(): string {
  return path.join(app.getPath('userData'), 'settings.json');
}
