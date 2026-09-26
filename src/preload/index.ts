// The only bridge between the sandboxed renderer and the main process.
// It exposes exactly the `M2CBridge` interface and nothing else.

import { contextBridge, ipcRenderer, webUtils } from 'electron';

import type {
  Canceled,
  DialogText,
  FileAction,
  KernelEvent,
  KernelRequest,
  KernelStatus,
  LogEntry,
  M2CBridge,
  RawResponse,
  RecoveryCandidate,
  TitleBarColors,
  Unsubscribe,
} from '@shared/bridge';
import { IPC } from '@shared/ipc';
import type { Settings, SettingsPatch } from '@shared/settings';

function subscribe<T>(channel: string, listener: (payload: T) => void): Unsubscribe {
  const handler = (_event: Electron.IpcRendererEvent, payload: T) => listener(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

const bridge: M2CBridge = {
  kernel: {
    request: (request: KernelRequest) =>
      ipcRenderer.invoke(IPC.kernelRequest, request) as Promise<RawResponse>,
    cancel: (clientId: number) => ipcRenderer.send(IPC.kernelCancel, clientId),
    restart: () => ipcRenderer.invoke(IPC.kernelRestart) as Promise<KernelStatus>,
    status: () => ipcRenderer.invoke(IPC.kernelGetStatus) as Promise<KernelStatus>,
    onEvent: (listener) => subscribe<KernelEvent>(IPC.kernelEvent, listener),
    onStatus: (listener) => subscribe<KernelStatus>(IPC.kernelStatus, listener),
  },
  files: {
    run: (action: FileAction, params: unknown, dialog: DialogText) =>
      ipcRenderer.invoke(IPC.filesRun, action, params, dialog) as Promise<RawResponse | Canceled>,
    dropped: (file: File) =>
      ipcRenderer.invoke(IPC.filesDropped, webUtils.getPathForFile(file)) as Promise<RawResponse>,
    openRecent: (recentId: string) =>
      ipcRenderer.invoke(IPC.filesOpenRecent, recentId) as Promise<RawResponse>,
    reveal: (token: string) => ipcRenderer.send(IPC.filesReveal, token),
  },
  recent: {
    list: () => ipcRenderer.invoke(IPC.recentList) as ReturnType<M2CBridge['recent']['list']>,
  },
  recovery: {
    list: () => ipcRenderer.invoke(IPC.recoveryList) as Promise<RecoveryCandidate[]>,
    resolve: (candidateId, action) =>
      ipcRenderer.invoke(IPC.recoveryResolve, candidateId, action) as Promise<KernelStatus>,
  },
  settings: {
    get: () => ipcRenderer.invoke(IPC.settingsGet) as Promise<Settings>,
    set: (patch: SettingsPatch) => ipcRenderer.invoke(IPC.settingsSet, patch) as Promise<Settings>,
  },
  window: {
    setTitleBarColors: (colors: TitleBarColors) =>
      ipcRenderer.send(IPC.windowSetTitleBarColors, colors),
    setTitle: (title: string) => ipcRenderer.send(IPC.windowSetTitle, title),
    onBeforeClose: (listener) => subscribe<void>(IPC.windowBeforeClose, listener),
    confirmClose: () => ipcRenderer.send(IPC.windowConfirmClose),
  },
  app: {
    info: () => ipcRenderer.invoke(IPC.appInfo) as ReturnType<M2CBridge['app']['info']>,
    log: (entry: LogEntry) => ipcRenderer.send(IPC.appLog, entry),
    openHelp: (language, topic) => ipcRenderer.send(IPC.appOpenHelp, language, topic),
    testMode: process.env.M2C_E2E === '1',
  },
};

contextBridge.exposeInMainWorld('m2c', bridge);
