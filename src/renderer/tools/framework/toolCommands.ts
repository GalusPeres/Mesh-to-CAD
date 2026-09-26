import type { AppCommand } from '../../app/commands/types';
import { TOOLS, isToolVisible, toolKey } from './registry';
import { openTool, toolAvailability } from './toolActions';

/** Every tool with a shortcut gets an "activate tool" command (viewport scope). */
export function toolActivationCommands(): AppCommand[] {
  return TOOLS.filter((tool) => tool.shortcut && isToolVisible(tool)).map((tool) => ({
    id: `tool.${tool.id}`,
    label: toolKey(tool.id, 'label'),
    icon: tool.icon,
    shortcuts: tool.shortcut ? [tool.shortcut] : [],
    scope: tool.shortcut?.ctrl ? 'global' : 'viewport',
    isEnabled: () => toolAvailability(tool).enabled,
    run: () => openTool(tool.id),
  }));
}
