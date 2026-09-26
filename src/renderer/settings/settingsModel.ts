import type { JsonValue } from '@shared/protocol/wireTypes';
import type { Settings, SettingsPatch } from '@shared/settings';

function isEmpty(value: JsonValue): boolean {
  if (value === null) return true;
  if (Array.isArray(value)) return value.length === 0;
  return typeof value === 'object' && Object.keys(value).length === 0;
}

/** Whether any tool remembers options (brush size, collapsed sections, ...). */
export function hasStoredToolOptions(settings: Settings): boolean {
  return Object.values(settings.tools).some((value) => !isEmpty(value));
}

/**
 * The patch that returns every tool to its default options. Settings patches merge
 * per tool id, so each stored entry is replaced by an empty object.
 */
export function resetToolOptionsPatch(settings: Settings): SettingsPatch | null {
  const stored = Object.entries(settings.tools).filter(([, value]) => !isEmpty(value));
  if (!stored.length) return null;
  return { tools: Object.fromEntries(stored.map(([toolId]) => [toolId, {}])) };
}
