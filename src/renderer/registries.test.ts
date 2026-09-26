// Checks of everything discovered from files: tools, commands, feature views and translations.

import { describe, expect, it } from 'vitest';

import {
  ERROR_CODES,
  FEATURE_TYPE_IDS,
  ISSUE_CODES,
  PROGRESS_STAGES,
} from '@shared/protocol/generated/index';

import { findShortcutConflicts } from './app/commands/keymap';
import { allCommands } from './app/commands/registry';
import { FEATURE_VIEWS } from './features/registry';
import { buildResources } from './i18n/resources';
import { STAGES } from './state/toolStore';
import { TOOLS, toolById } from './tools/framework/registry';

type Tree = Record<string, unknown>;

function keys(tree: unknown, prefix = ''): string[] {
  if (typeof tree !== 'object' || tree === null) return [prefix];
  return Object.entries(tree as Tree).flatMap(([key, value]) =>
    keys(value, prefix ? `${prefix}.${key}` : key),
  );
}

function lookup(tree: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((node, part) => (node as Tree | undefined)?.[part], tree);
}

/** i18next plural forms (`_one`, `_other`) count as the base key. */
function translated(namespace: unknown, key: string): boolean {
  return ['', '_one', '_other'].some(
    (suffix) => typeof lookup(namespace, key + suffix) === 'string',
  );
}

const resources = buildResources();
const de = resources.de as Tree;
const en = resources.en as Tree;

describe('translations', () => {
  it('have the same keys in German and English', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(de).sort());
    for (const namespace of Object.keys(de)) {
      expect(keys(en[namespace]).sort(), namespace).toEqual(keys(de[namespace]).sort());
    }
  });

  it.each([
    ['errors', ERROR_CODES],
    ['issues', ISSUE_CODES],
    ['progress', PROGRESS_STAGES],
  ] as const)('cover every kernel code in %s', (namespace, codes) => {
    for (const code of codes) {
      expect(translated(de[namespace], code), `${namespace}:${code} (de)`).toBe(true);
      expect(translated(en[namespace], code), `${namespace}:${code} (en)`).toBe(true);
    }
  });
});

describe('tools', () => {
  it('have unique ids, known stages and a label', () => {
    const ids = TOOLS.map((tool) => tool.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const tool of TOOLS) {
      expect(
        tool.stages.every((stage) => STAGES.includes(stage)),
        tool.id,
      ).toBe(true);
      const camel = tool.id.replace(/-([a-z0-9])/g, (_match, letter: string) =>
        letter.toUpperCase(),
      );
      expect(typeof lookup(de.tools, `${camel}.label`), tool.id).toBe('string');
    }
  });

  it('give every ready panel tool a panel', () => {
    for (const tool of TOOLS.filter(
      (candidate) => candidate.status === 'ready' && candidate.kind === 'panel',
    )) {
      expect(tool.Panel, tool.id).toBeDefined();
    }
  });
});

describe('feature views', () => {
  it('exist for every feature type, with a name and an existing edit tool', () => {
    for (const type of FEATURE_TYPE_IDS) {
      const view = FEATURE_VIEWS.get(type);
      expect(view, type).toBeDefined();
      expect(typeof lookup(de.features, `${type}.name`), type).toBe('string');
      if (view?.editTool) expect(toolById(view.editTool), type).toBeDefined();
    }
  });
});

describe('commands', () => {
  it('have unique ids, translated labels and no conflicting shortcuts', () => {
    const commands = allCommands();
    const ids = commands.map((command) => command.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(findShortcutConflicts(commands)).toEqual([]);
    for (const command of commands) {
      const [namespace = '', key = ''] = command.label.split(':');
      expect(typeof lookup(de[namespace], key), command.id).toBe('string');
    }
  });
});
