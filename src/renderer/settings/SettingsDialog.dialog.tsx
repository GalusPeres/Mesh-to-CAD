import { useTranslation } from 'react-i18next';
import { useStore } from 'zustand';

import type { Language, ThemeSetting } from '@shared/settings';

import { updateSettings, useSettings } from '../state/settingsStore';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { PropertyRow } from '../ui/PropertyRow/PropertyRow';
import { Select } from '../ui/Select/Select';
import { closeSettings, settingsDialogStore } from './settingsDialogStore';

const LANGUAGES: readonly Language[] = ['de', 'en'];
const THEMES: readonly ThemeSetting[] = ['system', 'dark', 'light'];

/** Language and theme; changes apply immediately. */
function SettingsDialog() {
  const { t } = useTranslation(['settings', 'common']);
  const open = useStore(settingsDialogStore, (state) => state.open);
  const language = useSettings((settings) => settings.language);
  const theme = useSettings((settings) => settings.theme);
  return (
    <Dialog
      open={open}
      title={t('title')}
      onOpenChange={(next) => {
        if (!next) closeSettings();
      }}
      footer={<Button onClick={closeSettings}>{t('common:actions.close')}</Button>}
    >
      <PropertyRow label={t('language')} htmlFor="settings-language">
        <Select
          id="settings-language"
          testId="settings-language"
          value={language}
          options={LANGUAGES.map((value) => ({ value, label: t(`common:language.${value}`) }))}
          onChange={(value) => void updateSettings({ language: value })}
        />
      </PropertyRow>
      <PropertyRow label={t('theme')} htmlFor="settings-theme">
        <Select
          id="settings-theme"
          testId="settings-theme"
          value={theme}
          options={THEMES.map((value) => ({ value, label: t(`common:theme.${value}`) }))}
          onChange={(value) => void updateSettings({ theme: value })}
        />
      </PropertyRow>
    </Dialog>
  );
}

export const dialog = SettingsDialog;
