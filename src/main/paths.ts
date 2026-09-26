import { tmpdir } from 'node:os';
import path from 'node:path';

import { app } from 'electron';

/** True when started by the end-to-end tests (`M2C_E2E=1`). */
export const testMode = process.env.M2C_E2E === '1';

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
  return path.join(base, 'Mesh-to-CAD');
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
