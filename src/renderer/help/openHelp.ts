import { i18n } from '../i18n';
import { toolStore } from '../state/toolStore';

export type HelpLanguage = 'de' | 'en';

export function helpLanguage(language: string): HelpLanguage {
  return language === 'en' ? 'en' : 'de';
}

/** The help page for the open panel tool, else the active selection mode, else the index. */
export function activeHelpTopic(): string {
  const { activeToolId, selectionMode } = toolStore.getState();
  return activeToolId ?? selectionMode ?? 'index';
}

/** Open a bundled help page (`resources/help/<language>/<topic>.html`) in the browser. */
export function openHelp(topic: string = activeHelpTopic()): void {
  window.m2c.app.openHelp(helpLanguage(i18n.language), topic);
}
