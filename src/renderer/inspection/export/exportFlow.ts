// Export through the main process: the renderer names the action and the dialog texts,
// main shows the save dialog and calls the main-only kernel method with the path.

import type { DialogText } from '@shared/bridge';
import type { ExportResult } from '@shared/protocol/generated/export';

import { KernelFailure } from '../../kernel/KernelFailure';

export interface ExportOutcome {
  result: ExportResult;
  /** Lets `files.reveal` show the file in Explorer, when the main process provides it. */
  revealToken: string | null;
}

/** Null when the user cancelled the dialog; throws a `KernelFailure` when export failed. */
export async function runExport(
  action: 'exportStep' | 'exportStl',
  params: Record<string, unknown>,
  dialog: DialogText,
): Promise<ExportOutcome | null> {
  const response = await window.m2c.files.run(action, params, dialog);
  if ('canceled' in response) return null;
  if (!response.ok) throw new KernelFailure(response.error);
  const token = (response as { revealToken?: unknown }).revealToken;
  return {
    result: response.result as ExportResult,
    revealToken: typeof token === 'string' ? token : null,
  };
}

/** Product names: the project name, followed by the body name when there are several. */
export function productNames(
  project: string,
  bodies: readonly string[],
  names: ReadonlyMap<string, string>,
  combine: (project: string, body: string) => string,
): string[] {
  if (bodies.length === 1) return [project];
  return bodies.map((body) => combine(project, names.get(body) ?? body));
}

const FORBIDDEN = new Set(['<', '>', ':', '"', '/', '\\', '|', '?', '*']);

/** A default file name without the characters Windows does not allow. */
export function safeFileName(name: string): string {
  const cleaned = Array.from(name, (char) => (FORBIDDEN.has(char) || char < ' ' ? '_' : char))
    .join('')
    .trim();
  return cleaned || 'export';
}
