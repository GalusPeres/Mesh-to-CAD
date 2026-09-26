// The design rules of docs/DESIGN.md that can be checked mechanically.

import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { TITLE_BAR_COLORS } from '@shared/theme';

const RENDERER = path.resolve(import.meta.dirname, '..');
const COLOR_FILES = new Set(['styles/tokens.css', 'viewport/palette.ts']);
const HEX_COLOR = /#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/;

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(css|tsx?)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

const files = sourceFiles(RENDERER).map((file) => ({
  name: path.relative(RENDERER, file).replaceAll('\\', '/'),
  text: readFileSync(file, 'utf8'),
}));

describe('design rules', () => {
  it('keep colour literals in tokens.css and palette.ts', () => {
    const offenders = files.filter(
      (file) => !COLOR_FILES.has(file.name) && HEX_COLOR.test(file.text),
    );
    expect(offenders.map((file) => file.name)).toEqual([]);
  });

  it('use no gradients, blur effects or glows', () => {
    const offenders = files.filter((file) =>
      /gradient\(|backdrop-filter|text-shadow|filter:\s*blur/.test(file.text),
    );
    expect(offenders.map((file) => file.name)).toEqual([]);
  });

  it('never set text below 12 px (the view cube uses a token)', () => {
    const small = /font-size:\s*(\d+(?:\.\d+)?)px/g;
    const offenders = files.flatMap((file) =>
      [...file.text.matchAll(small)].filter((match) => Number(match[1]) < 12).map(() => file.name),
    );
    expect(offenders).toEqual([]);
  });

  it('keep radii at 4 px or below', () => {
    const offenders = files.flatMap((file) =>
      [...file.text.matchAll(/border-radius:\s*(\d+)px/g)]
        .filter((match) => Number(match[1]) > 4)
        .map(() => file.name),
    );
    expect(offenders).toEqual([]);
  });

  it('match the title-bar colours of the main process with the tokens', () => {
    const tokens = readFileSync(path.join(RENDERER, 'styles/tokens.css'), 'utf8').toLowerCase();
    const block = (theme: string) => tokens.slice(tokens.indexOf(`[data-theme='${theme}']`));
    for (const theme of ['dark', 'light'] as const) {
      const colors = TITLE_BAR_COLORS[theme];
      expect(block(theme)).toContain(`--bg-app: ${colors.color.toLowerCase()}`);
      expect(block(theme)).toContain(`--text: ${colors.symbolColor.toLowerCase()}`);
    }
  });
});
