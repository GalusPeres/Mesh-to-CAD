import { existsSync } from 'node:fs';
import path from 'node:path';

import {
  type BrowserWindow,
  type IpcMainEvent,
  type IpcMainInvokeEvent,
  app,
  ipcMain,
  shell,
} from 'electron';

import type {
  AppInfo,
  KernelEvent,
  KernelRequest,
  KernelStatus,
  LogEntry,
  RawResponse,
  RecoveryCandidate,
} from '@shared/bridge';
import { IPC } from '@shared/ipc';
import { METHOD_TABLE } from '@shared/protocol/generated/index';

import type { FileActions } from './files';
import { isFileAction } from './files';
import type { KernelHost } from './kernel/KernelHost';
import type { Logger } from './logging';
import type { RecentFiles } from './recent';
import type { SettingsStore } from './settings';

export interface RecoveryActions {
  list: () => RecoveryCandidate[];
  resolve: (candidateId: string, action: 'restore' | 'discard') => Promise<KernelStatus>;
}

const HELP_TOPIC = /^[a-z0-9-]{1,64}$/;

export interface IpcContext {
  window: () => BrowserWindow | null;
  allowedOrigin: string;
  kernel: KernelHost;
  files: FileActions;
  recent: RecentFiles;
  recovery: RecoveryActions;
  settings: SettingsStore;
  log: Logger;
  logDirectory: string;
  /** Folder with `help/<language>/<topic>.html`. */
  resourcesDirectory: string;
  onSettingsChanged: () => void;
  onConfirmClose: () => void;
}

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

function methodCallableByRenderer(method: string): boolean {
  const info = (METHOD_TABLE as Record<string, { caller: string } | undefined>)[method];
  return info?.caller === 'renderer';
}

/** Register every IPC handler. Each one first checks that the sender is our own page. */
export function registerIpc(context: IpcContext): void {
  const trusted = (event: IpcMainEvent | IpcMainInvokeEvent): boolean => {
    const window = context.window();
    const frame = event.senderFrame;
    if (
      !window ||
      event.sender !== window.webContents ||
      !frame ||
      frame !== window.webContents.mainFrame
    ) {
      return false;
    }
    // URL.origin is "null" for custom schemes such as m2c://, so compare scheme and host.
    const url = new URL(frame.url);
    return `${url.protocol}//${url.host}` === context.allowedOrigin;
  };

  const handle = <T>(
    channel: string,
    handler: (event: IpcMainInvokeEvent, ...args: unknown[]) => T,
  ) => {
    ipcMain.handle(channel, (event, ...args: unknown[]) => {
      if (!trusted(event)) throw new Error('Rejected IPC call from an untrusted sender.');
      return handler(event, ...args);
    });
  };

  const on = (channel: string, handler: (event: IpcMainEvent, ...args: unknown[]) => void) => {
    ipcMain.on(channel, (event, ...args: unknown[]) => {
      if (trusted(event)) handler(event, ...args);
    });
  };

  const send = (channel: string, payload: unknown) => {
    const window = context.window();
    if (window && !window.isDestroyed()) window.webContents.send(channel, payload);
  };

  // Maps the renderer's client ids to kernel request ids, for cancellation.
  const running = new Map<number, number>();

  handle(IPC.kernelRequest, async (_event, raw): Promise<RawResponse> => {
    const request = raw as KernelRequest;
    if (typeof request?.method !== 'string' || typeof request.clientId !== 'number') {
      return { ok: false, error: { code: 'kernel.invalidParams', params: {} } };
    }
    if (!methodCallableByRenderer(request.method)) {
      return {
        ok: false,
        error: { code: 'kernel.notAllowed', params: { method: request.method } },
      };
    }
    const buffers = (request.buffers ?? []).map((buffer) => new Uint8Array(buffer));
    const { id, response } = context.kernel.request(
      {
        method: request.method,
        params: request.params,
        buffers,
        lane: request.lane,
        origin: 'renderer',
      },
      (fraction, stage) => {
        const event: KernelEvent = {
          type: 'progress',
          clientId: request.clientId,
          fraction,
          stage,
        };
        send(IPC.kernelEvent, event);
      },
    );
    running.set(request.clientId, id);
    try {
      return await response;
    } finally {
      running.delete(request.clientId);
    }
  });

  on(IPC.kernelCancel, (_event, clientId) => {
    const id = running.get(Number(clientId));
    if (id !== undefined) context.kernel.cancel(id);
  });

  handle(IPC.kernelRestart, async (): Promise<KernelStatus> => {
    await context.kernel
      .restart()
      .catch((error: unknown) => context.log.error('kernel restart failed', error));
    return context.kernel.status;
  });

  handle(IPC.kernelGetStatus, () => context.kernel.status);

  context.kernel.onStatus((status) => send(IPC.kernelStatus, status));
  context.kernel.onDocumentChanged((data) => {
    const event: KernelEvent = { type: 'documentChanged', data };
    send(IPC.kernelEvent, event);
  });

  handle(IPC.filesRun, (_event, action, params, text) => {
    if (!isFileAction(action)) throw new Error('Unknown file action.');
    const dialogText = (text ?? {}) as {
      title?: unknown;
      filterName?: unknown;
      defaultName?: unknown;
    };
    return context.files.run(action, params, {
      title: typeof dialogText.title === 'string' ? dialogText.title : '',
      filterName: typeof dialogText.filterName === 'string' ? dialogText.filterName : '',
      defaultName: typeof dialogText.defaultName === 'string' ? dialogText.defaultName : undefined,
    });
  });
  on(IPC.filesReveal, (_event, token) => {
    const file = context.files.revealPath(token);
    if (file && existsSync(file)) shell.showItemInFolder(file);
  });
  handle(IPC.filesDropped, (_event, filePath) => context.files.openDropped(filePath));
  handle(IPC.filesOpenRecent, (_event, recentId) => context.files.openRecent(recentId));
  handle(IPC.recentList, () => context.recent.list());
  handle(IPC.recoveryList, () => context.recovery.list());
  handle(IPC.recoveryResolve, (_event, candidateId, action) => {
    if (typeof candidateId !== 'string' || (action !== 'restore' && action !== 'discard')) {
      throw new Error('Invalid recovery request.');
    }
    return context.recovery.resolve(candidateId, action);
  });

  handle(IPC.settingsGet, () => context.settings.get());
  handle(IPC.settingsSet, (_event, patch) => {
    // The store validates every value; anything malformed falls back to the defaults.
    const updated = context.settings.update(
      typeof patch === 'object' && patch !== null ? patch : {},
    );
    context.onSettingsChanged();
    return updated;
  });

  on(IPC.windowSetTitleBarColors, (_event, colors) => {
    const { color, symbolColor } = (colors ?? {}) as { color?: unknown; symbolColor?: unknown };
    const window = context.window();
    if (typeof color !== 'string' || typeof symbolColor !== 'string') return;
    if (window && HEX_COLOR.test(color) && HEX_COLOR.test(symbolColor)) {
      window.setTitleBarOverlay({ color, symbolColor });
      window.setBackgroundColor(color);
    }
  });
  on(IPC.windowSetTitle, (_event, title) => {
    if (typeof title === 'string') context.window()?.setTitle(title.slice(0, 200));
  });
  on(IPC.windowConfirmClose, () => context.onConfirmClose());

  handle(IPC.appInfo, (): AppInfo => ({
    version: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
    platform: `${process.platform} ${process.arch}`,
    logDirectory: context.logDirectory,
  }));
  on(IPC.appOpenHelp, (_event, language, topic) => {
    if ((language !== 'de' && language !== 'en') || typeof topic !== 'string') return;
    const helpDirectory = path.join(context.resourcesDirectory, 'help', language);
    const page = path.join(helpDirectory, `${HELP_TOPIC.test(topic) ? topic : 'index'}.html`);
    const target = existsSync(page) ? page : path.join(helpDirectory, 'index.html');
    if (!existsSync(target)) {
      context.log.warn(`help page missing: ${target}`);
      return;
    }
    void shell.openPath(target).then((error) => {
      if (error) context.log.warn(`could not open help page: ${error}`);
    });
  });
  on(IPC.appLog, (_event, entry) => {
    const { level, message, stack } = (entry ?? {}) as Partial<LogEntry>;
    const text = `[renderer] ${String(message ?? '')}${stack ? `\n${stack}` : ''}`;
    if (level === 'error') context.log.error(text);
    else if (level === 'warn') context.log.warn(text);
    else context.log.info(text);
  });
}
