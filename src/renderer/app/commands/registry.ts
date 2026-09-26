// Commands are discovered from every `*.commands.ts` file of the renderer, so a
// module adds menu entries and shortcuts without touching a shared file.

import { toolActivationCommands } from '../../tools/framework/toolCommands';
import type { AppCommand, MenuId } from './types';

const modules = import.meta.glob<{ commands: readonly AppCommand[] }>('../../**/*.commands.ts', {
  eager: true,
});

let cache: readonly AppCommand[] | null = null;

export function allCommands(): readonly AppCommand[] {
  cache ??= [
    ...Object.values(modules).flatMap((module) => module.commands),
    ...toolActivationCommands(),
  ];
  return cache;
}

export function commandById(id: string): AppCommand | undefined {
  return allCommands().find((command) => command.id === id);
}

/** Commands of one menu, grouped and ordered. */
export function menuGroups(menu: MenuId): AppCommand[][] {
  const placed = allCommands().filter((command) => command.placement?.menu === menu);
  const groups = new Map<number, AppCommand[]>();
  for (const command of placed) {
    const group = command.placement?.group ?? 0;
    groups.set(group, [...(groups.get(group) ?? []), command]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([, items]) =>
      items.sort((a, b) => (a.placement?.order ?? 0) - (b.placement?.order ?? 0)),
    );
}

export async function runCommand(command: AppCommand): Promise<void> {
  if (command.isEnabled && !command.isEnabled()) return;
  await command.run();
}
