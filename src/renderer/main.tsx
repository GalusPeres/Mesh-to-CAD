import './styles/tokens.css';
import './styles/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { AppShell } from './app/AppShell';
import { applyTheme, watchSystemTheme } from './app/theme';
import { initI18n, setLanguage } from './i18n';
import { startDocumentSync } from './kernel/documentSync';
import { loadSettings, settingsStore } from './state/settingsStore';
import { installTestHooks } from './testing/testHooks';
import { TooltipProvider } from './ui/Tooltip/Tooltip';

async function start(): Promise<void> {
  const bridge = window.m2c;
  const settings = await bridge.settings.get();
  loadSettings(settings);
  applyTheme(settings.theme);
  await initI18n(settings.language);

  settingsStore.subscribe((current, previous) => {
    if (current.language !== previous.language) void setLanguage(current.language);
    if (current.theme !== previous.theme) applyTheme(current.theme);
  });
  watchSystemTheme(() => settingsStore.getState().theme);
  window.addEventListener('error', (event) =>
    bridge.app.log({ level: 'error', message: event.message }),
  );
  window.addEventListener('unhandledrejection', (event) =>
    bridge.app.log({ level: 'error', message: String(event.reason) }),
  );
  bridge.window.onBeforeClose(() => bridge.window.confirmClose());

  startDocumentSync();
  if (bridge.app.testMode) installTestHooks();

  const root = document.getElementById('root');
  if (!root) throw new Error('missing #root element');
  createRoot(root).render(
    <StrictMode>
      <TooltipProvider>
        <AppShell />
      </TooltipProvider>
    </StrictMode>,
  );
}

void start();
