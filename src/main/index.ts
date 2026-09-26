import path from 'node:path';

import { type BrowserWindow, app, nativeTheme, session } from 'electron';

import { IPC } from '@shared/ipc';
import { TITLE_BAR_COLORS } from '@shared/theme';

import { APP_ORIGIN, APP_URL, registerAppScheme, serveRenderer } from './appProtocol';
import { AutomationServer } from './automation';
import { FileActions } from './files';
import { registerIpc } from './ipc';
import { KernelHost } from './kernel/KernelHost';
import { locateKernel } from './kernel/locate';
import { FileLogger } from './logging';
import {
  logDirectory,
  rendererDirectory,
  repositoryRoot,
  resourcesDirectory,
  sessionsDirectory,
  settingsPath,
  testMode,
} from './paths';
import { RecentFiles } from './recent';
import { candidateDirectory, deleteSession, findRecoveryCandidates } from './recovery';
import { PRODUCTION_CSP, developmentUrl, hardenSession } from './security';
import { SettingsStore } from './settings';
import { createMainWindow } from './window';

if (testMode) {
  // CI machines have no GPU; SwiftShader keeps WebGL available for the end-to-end tests.
  // The viewport performance test measures the real GPU instead (`M2C_E2E_GPU=1`).
  if (process.env.M2C_E2E_GPU !== '1') {
    app.commandLine.appendSwitch('use-angle', 'swiftshader');
    app.commandLine.appendSwitch('enable-unsafe-swiftshader');
  }
  app.setPath(
    'userData',
    path.join(app.getPath('temp'), 'mesh-to-cad-e2e-profile', String(process.pid)),
  );
}

registerAppScheme();

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  void app.whenReady().then(startApplication);
}

let mainWindow: BrowserWindow | null = null;

function startApplication(): void {
  const log = new FileLogger(logDirectory(), 'main');
  const kernelLog = new FileLogger(logDirectory(), 'kernel');
  process.on('uncaughtException', (error) => log.error('uncaught exception', error));

  const devUrl = developmentUrl();
  const devOrigin = devUrl ? new URL(devUrl).origin : null;
  hardenSession(session.defaultSession, devOrigin);
  if (!devUrl) serveRenderer(rendererDirectory(), PRODUCTION_CSP);

  const settings = new SettingsStore(settingsPath(), log);
  // A restore after a crash switches to the crashed session's directory (recovery.ts).
  let sessionDirectory = path.join(sessionsDirectory(), `${Date.now()}-${process.pid}`);
  const kernel = new KernelHost({
    locate: () =>
      locateKernel({
        packaged: app.isPackaged,
        resourcesPath: process.resourcesPath,
        repositoryRoot: repositoryRoot(),
        sessionDirectory,
      }),
    log,
    onKernelLog: (line) => kernelLog.raw(line),
  });
  const recent = new RecentFiles();
  const examplesDirectory = path.join(resourcesDirectory(), 'examples');
  const files = new FileActions({
    window: () => mainWindow,
    kernel,
    recent,
    examplesDirectory,
    log,
  });

  const recoveryCandidates = findRecoveryCandidates(sessionsDirectory(), sessionDirectory);
  const recovery = {
    list: () => recoveryCandidates,
    resolve: async (candidateId: string, action: 'restore' | 'discard') => {
      const directory = candidateDirectory(sessionsDirectory(), recoveryCandidates, candidateId);
      if (!directory) throw new Error('Unknown recovery candidate.');
      recoveryCandidates.splice(
        recoveryCandidates.findIndex((candidate) => candidate.id === candidateId),
        1,
      );
      if (action === 'discard') {
        deleteSession(directory);
        return kernel.status;
      }
      const abandoned = sessionDirectory;
      sessionDirectory = directory;
      await kernel.restart();
      deleteSession(abandoned);
      return kernel.status;
    },
  };

  const automation = new AutomationServer({
    kernel,
    window: () => mainWindow,
    log,
    infoPath: path.join(app.getPath('userData'), 'automation.json'),
    version: app.getVersion(),
  });
  const syncAutomation = () => {
    const wanted = settings.get().automation.enabled || process.env.M2C_AUTOMATION === '1';
    const change = wanted ? automation.start() : automation.stop();
    change.catch((error: unknown) => log.error('automation interface', error));
  };

  let closeConfirmed = false;
  registerIpc({
    window: () => mainWindow,
    allowedOrigin: devOrigin ?? APP_ORIGIN,
    kernel,
    files,
    recent,
    recovery,
    settings,
    log,
    logDirectory: logDirectory(),
    resourcesDirectory: resourcesDirectory(),
    onSettingsChanged: () => {
      nativeTheme.themeSource = settings.get().theme;
      syncAutomation();
    },
    onConfirmClose: () => {
      closeConfirmed = true;
      mainWindow?.close();
    },
  });

  nativeTheme.themeSource = settings.get().theme;
  mainWindow = createMainWindow(settings.get(), devUrl ?? APP_URL);
  mainWindow.on('close', (event) => {
    // The renderer decides about unsaved changes and answers with window:confirmClose.
    if (closeConfirmed || testMode || !mainWindow) return;
    event.preventDefault();
    mainWindow.webContents.send(IPC.windowBeforeClose);
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
  nativeTheme.on('updated', () => {
    if (!mainWindow || settings.get().theme !== 'system') return;
    const colors = TITLE_BAR_COLORS[nativeTheme.shouldUseDarkColors ? 'dark' : 'light'];
    mainWindow.setTitleBarOverlay(colors);
  });

  app.on('second-instance', () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  let quitting = false;
  app.on('before-quit', (event) => {
    if (quitting) return;
    quitting = true;
    event.preventDefault();
    void Promise.allSettled([automation.stop(), kernel.stop()]).finally(() => {
      // Delete the session only after the kernel exited: Windows cannot remove
      // files that another process still has open.
      deleteSession(sessionDirectory);
      log.info('application closed');
      app.quit();
    });
  });
  app.on('window-all-closed', () => app.quit());

  kernel.start().catch((error: unknown) => log.error('kernel start failed', error));
  syncAutomation();
}
