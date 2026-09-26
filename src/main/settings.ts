import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import {
  DEFAULT_SETTINGS,
  type Settings,
  type SettingsPatch,
  applySettingsPatch,
  validateSettings,
} from '@shared/settings';

import type { Logger } from './logging';

/** Preferences in a JSON file; a missing or damaged file yields the defaults. */
export class SettingsStore {
  private current: Settings;

  constructor(
    private readonly file: string,
    private readonly log: Logger,
  ) {
    this.current = this.read();
  }

  get(): Settings {
    return this.current;
  }

  update(patch: SettingsPatch): Settings {
    this.current = applySettingsPatch(this.current, patch);
    this.write();
    return this.current;
  }

  private read(): Settings {
    try {
      return validateSettings(JSON.parse(readFileSync(this.file, 'utf8')));
    } catch {
      return structuredClone(DEFAULT_SETTINGS);
    }
  }

  private write(): void {
    try {
      mkdirSync(path.dirname(this.file), { recursive: true });
      const temporary = `${this.file}.tmp`;
      writeFileSync(temporary, JSON.stringify(this.current, null, 2), 'utf8');
      renameSync(temporary, this.file);
    } catch (error) {
      this.log.error('could not save settings', error);
    }
  }
}
