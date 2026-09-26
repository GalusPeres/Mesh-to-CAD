// The API the preload script exposes to the renderer as `window.m2c`.
// The renderer never sees file paths: every file operation goes through a
// named action that the main process carries out after a native dialog.

import type { Settings, SettingsPatch } from './settings';

export type Unsubscribe = () => void;

export interface KernelRequest {
  clientId: number;
  method: string;
  params: unknown;
  buffers: ArrayBuffer[];
  lane?: string;
}

export interface KernelErrorPayload {
  code: string;
  params: Record<string, unknown>;
  details?: string;
}

export type RawResponse =
  | { ok: true; result: unknown; buffers: ArrayBuffer[]; revealToken?: string }
  | { ok: false; error: KernelErrorPayload };

export type KernelEvent =
  | { type: 'progress'; clientId: number; fraction: number | null; stage: string }
  | { type: 'documentChanged'; data: unknown };

export type KernelState = 'starting' | 'ready' | 'unresponsive' | 'stopped';

export interface KernelStatus {
  state: KernelState;
  exitCode?: number | null;
  error?: KernelErrorPayload;
}

export type FileAction =
  | 'openMesh'
  | 'openExample'
  | 'openProject'
  | 'saveProject'
  | 'saveProjectAs'
  | 'exportStep'
  | 'exportStl'
  | 'exportReport';

/** Dialog texts come from the renderer, already translated. */
export interface DialogText {
  title: string;
  filterName: string;
  /** Suggested file name for save dialogs (no folder). */
  defaultName?: string;
}

export interface Canceled {
  canceled: true;
}

export interface RecentFile {
  id: string;
  name: string;
  folder: string;
  kind: 'mesh' | 'project';
  openedAt: number;
}

export interface RecoveryCandidate {
  id: string;
  startedAt: number;
  label: string;
}

export interface AppInfo {
  version: string;
  electron: string;
  chrome: string;
  node: string;
  platform: string;
  logDirectory: string;
}

export interface LogEntry {
  level: 'info' | 'warn' | 'error';
  message: string;
  stack?: string;
}

export interface TitleBarColors {
  color: string;
  symbolColor: string;
}

export interface M2CBridge {
  kernel: {
    request(request: KernelRequest): Promise<RawResponse>;
    cancel(clientId: number): void;
    restart(): Promise<KernelStatus>;
    status(): Promise<KernelStatus>;
    onEvent(listener: (event: KernelEvent) => void): Unsubscribe;
    onStatus(listener: (status: KernelStatus) => void): Unsubscribe;
  };
  files: {
    run(action: FileAction, params: unknown, dialog: DialogText): Promise<RawResponse | Canceled>;
    dropped(file: File): Promise<RawResponse>;
    openRecent(recentId: string): Promise<RawResponse>;
    reveal(token: string): void;
  };
  recent: {
    list(): Promise<RecentFile[]>;
  };
  recovery: {
    /** Sessions left by a crashed instance, found at start. */
    list(): Promise<RecoveryCandidate[]>;
    resolve(candidateId: string, action: 'restore' | 'discard'): Promise<KernelStatus>;
  };
  settings: {
    get(): Promise<Settings>;
    set(patch: SettingsPatch): Promise<Settings>;
  };
  window: {
    setTitleBarColors(colors: TitleBarColors): void;
    setTitle(title: string): void;
    onBeforeClose(listener: () => void): Unsubscribe;
    confirmClose(): void;
  };
  app: {
    info(): Promise<AppInfo>;
    log(entry: LogEntry): void;
    /** Open the bundled help page of a topic (a tool id or 'index') in the default browser. */
    openHelp(language: 'de' | 'en', topic: string): void;
    /** True when started for end-to-end tests (`M2C_E2E=1`); enables test hooks. */
    testMode: boolean;
  };
}
