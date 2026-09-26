// Tools are discovered from `tools/<tool-id>/index.ts`; each exports `tool`.

import type { StageId } from '../../state/toolStore';
import type { ToolDefinition } from './types';

const modules = import.meta.glob<{ tool: ToolDefinition }>('../*/index.ts', { eager: true });

function folderOf(file: string): string {
  return file.split('/').at(-2) ?? '';
}

export const TOOLS: readonly ToolDefinition[] = Object.entries(modules)
  .filter(([file]) => folderOf(file) !== 'framework')
  .map(([file, module]) => {
    if (module.tool.id !== folderOf(file)) {
      throw new Error(`Tool id ${module.tool.id} does not match its folder ${folderOf(file)}.`);
    }
    return module.tool;
  });

/** Planned tools are shown (disabled) only in development builds. */
export const SHOW_PLANNED_TOOLS = import.meta.env.DEV;

export function toolById(id: string): ToolDefinition | undefined {
  return TOOLS.find((tool) => tool.id === id);
}

export function isToolVisible(tool: ToolDefinition): boolean {
  return tool.status === 'ready' || SHOW_PLANNED_TOOLS;
}

export function toolsForStage(stage: StageId): ToolDefinition[] {
  return TOOLS.filter((tool) => tool.stages.includes(stage) && isToolVisible(tool));
}

/** i18n key of a tool string, e.g. `tools:selectBrush.label`. */
export function toolKey(toolId: string, key: string): string {
  const camel = toolId.replace(/-([a-z0-9])/g, (_match, letter: string) => letter.toUpperCase());
  return `tools:${camel}.${key}`;
}
