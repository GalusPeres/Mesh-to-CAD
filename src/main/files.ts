import { existsSync, statSync } from 'node:fs';
import path from 'node:path';

import { type BrowserWindow, dialog } from 'electron';

import type { Canceled, DialogText, FileAction, RawResponse } from '@shared/bridge';

import type { KernelHost } from './kernel/KernelHost';
import type { Logger } from './logging';
import type { RecentFiles } from './recent';

interface FileActionSpec {
  /** Kernel method that receives the chosen path; callable only by the main process. */
  method: string;
  dialog: 'open' | 'save' | 'example';
  extensions: readonly string[];
  recent?: 'mesh' | 'project';
}

/** Every file operation the renderer can request. The renderer never supplies a path. */
export const FILE_ACTIONS: Record<FileAction, FileActionSpec> = {
  openMesh: {
    method: 'mesh.import',
    dialog: 'open',
    extensions: ['stl', 'obj', 'ply'],
    recent: 'mesh',
  },
  openExample: { method: 'mesh.import', dialog: 'example', extensions: ['stl'] },
  openProject: { method: 'project.load', dialog: 'open', extensions: ['m2c'], recent: 'project' },
  saveProject: { method: 'project.save', dialog: 'save', extensions: ['m2c'], recent: 'project' },
  saveProjectAs: { method: 'project.save', dialog: 'save', extensions: ['m2c'], recent: 'project' },
  exportStep: { method: 'export.step', dialog: 'save', extensions: ['step', 'stp'] },
  exportStl: { method: 'export.stl', dialog: 'save', extensions: ['stl'] },
  exportReport: { method: 'inspection.report', dialog: 'save', extensions: ['csv'] },
};

const MESH_EXTENSIONS = new Set(['.stl', '.obj', '.ply']);
const PROJECT_EXTENSIONS = new Set(['.m2c']);
const EXAMPLE_ID = /^[a-z0-9-]{1,40}$/;

export function isFileAction(value: unknown): value is FileAction {
  return typeof value === 'string' && Object.hasOwn(FILE_ACTIONS, value);
}

export interface FileActionContext {
  window: () => BrowserWindow | null;
  kernel: KernelHost;
  recent: RecentFiles;
  examplesDirectory: string;
  log: Logger;
}

export class FileActions {
  private readonly lastFolder = new Map<FileAction, string>();

  constructor(private readonly context: FileActionContext) {}

  async run(
    action: FileAction,
    params: unknown,
    text: DialogText,
  ): Promise<RawResponse | Canceled> {
    const spec = FILE_ACTIONS[action];
    const extra =
      typeof params === 'object' && params !== null ? (params as Record<string, unknown>) : {};
    const chosen = await this.choosePath(action, spec, extra, text);
    if (chosen === null) return { canceled: true };
    if (spec.dialog !== 'example') this.lastFolder.set(action, path.dirname(chosen));
    const { exampleId: _exampleId, ...rest } = extra;
    const response = await this.callKernel(spec.method, { ...rest, path: chosen });
    if (response.ok && spec.recent) this.context.recent.remember(chosen, spec.recent);
    return response;
  }

  /** A file dropped onto the window: meshes are imported, projects opened. */
  async openDropped(filePath: unknown): Promise<RawResponse> {
    if (typeof filePath !== 'string' || !existsSync(filePath) || !statSync(filePath).isFile()) {
      return { ok: false, error: { code: 'mesh.fileNotFound', params: {} } };
    }
    const extension = path.extname(filePath).toLowerCase();
    if (MESH_EXTENSIONS.has(extension)) return this.callKernel('mesh.import', { path: filePath });
    if (PROJECT_EXTENSIONS.has(extension))
      return this.callKernel('project.load', { path: filePath });
    return { ok: false, error: { code: 'mesh.unsupportedFormat', params: { suffix: extension } } };
  }

  async openRecent(recentId: unknown): Promise<RawResponse> {
    const filePath = typeof recentId === 'string' ? this.context.recent.resolve(recentId) : null;
    return this.openDropped(filePath);
  }

  private async choosePath(
    action: FileAction,
    spec: FileActionSpec,
    params: Record<string, unknown>,
    text: DialogText,
  ): Promise<string | null> {
    if (spec.dialog === 'example') {
      const id = params.exampleId;
      if (typeof id !== 'string' || !EXAMPLE_ID.test(id)) return null;
      const file = path.join(this.context.examplesDirectory, `${id}.stl`);
      return existsSync(file) ? file : null;
    }
    const window = this.context.window();
    const filters = [{ name: text.filterName, extensions: [...spec.extensions] }];
    const folder = this.lastFolder.get(action);
    if (spec.dialog === 'open') {
      const options = {
        title: text.title,
        filters,
        properties: ['openFile' as const],
        defaultPath: folder,
      };
      const result = window
        ? await dialog.showOpenDialog(window, options)
        : await dialog.showOpenDialog(options);
      return result.canceled ? null : (result.filePaths[0] ?? null);
    }
    const name = text.defaultName ? path.basename(text.defaultName) : undefined;
    const defaultPath = folder && name ? path.join(folder, name) : (name ?? folder);
    const options = { title: text.title, filters, defaultPath };
    const result = window
      ? await dialog.showSaveDialog(window, options)
      : await dialog.showSaveDialog(options);
    return result.canceled ? null : (result.filePath ?? null);
  }

  private async callKernel(method: string, params: Record<string, unknown>): Promise<RawResponse> {
    this.context.log.info(`file action ${method}`);
    return this.context.kernel.request({ method, params, origin: 'main' }).response;
  }
}
