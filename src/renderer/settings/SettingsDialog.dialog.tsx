import { useTranslation } from 'react-i18next';

import type { Language, ThemeSetting } from '@shared/settings';

import { showMessage } from '../state/messageStore';
import { settingsStore, updateSettings, useSettings } from '../state/settingsStore';
import { Button } from '../ui/Button/Button';
import { Checkbox } from '../ui/Checkbox/Checkbox';
import { Dialog } from '../ui/Dialog/Dialog';
import { PropertyRow } from '../ui/PropertyRow/PropertyRow';
import { Select } from '../ui/Select/Select';
import { closeDialog, useOpenDialog } from './appDialogStore';
import styles from './SettingsDialog.module.css';
import { hasStoredToolOptions, resetToolOptionsPatch } from './settingsModel';

const LANGUAGES: readonly Language[] = ['de', 'en'];
const THEMES: readonly ThemeSetting[] = ['system', 'dark', 'light'];

async function resetToolOptions(message: string): Promise<void> {
  const patch = resetToolOptionsPatch(settingsStore.getState());
  if (!patch) return;
  await updateSettings(patch);
  showMessage('success', message);
}

/**
 * Application preferences. Every change applies at once and is stored by the main
 * process; project values such as the tolerance live in the document instead.
 */
function SettingsDialog() {
  const { t } = useTranslation(['settings', 'common']);
  const open = useOpenDialog() === 'settings';
  const settings = useSettings((current) => current);

  return (
    <Dialog
      open={open}
      title={t('title')}
      onOpenChange={(next) => {
        if (!next) closeDialog();
      }}
      footer={
        <Button variant="primary" data-testid="settings-close" onClick={closeDialog}>
          {t('common:actions.close')}
        </Button>
      }
    >
      <h3 className={styles.heading}>{t('general')}</h3>
      <PropertyRow label={t('language')} htmlFor="settings-language">
        <Select
          id="settings-language"
          testId="settings-language"
          value={settings.language}
          options={LANGUAGES.map((value) => ({ value, label: t(`common:language.${value}`) }))}
          onChange={(value) => void updateSettings({ language: value })}
        />
      </PropertyRow>
      <PropertyRow label={t('theme')} htmlFor="settings-theme">
        <Select
          id="settings-theme"
          testId="settings-theme"
          value={settings.theme}
          options={THEMES.map((value) => ({ value, label: t(`common:theme.${value}`) }))}
          onChange={(value) => void updateSettings({ theme: value })}
        />
      </PropertyRow>

      <h3 className={styles.heading}>{t('navigation')}</h3>
      <Checkbox
        checked={settings.navigation.invertWheel}
        label={t('invertWheel')}
        testId="settings-invert-wheel"
        onChange={(invertWheel) => void updateSettings({ navigation: { invertWheel } })}
      />

      <h3 className={styles.heading}>{t('selection')}</h3>
      <Checkbox
        checked={settings.selection.clearAfterFit}
        label={t('clearAfterFit')}
        testId="settings-clear-after-fit"
        onChange={(clearAfterFit) => void updateSettings({ selection: { clearAfterFit } })}
      />

      <h3 className={styles.heading}>{t('automation')}</h3>
      <Checkbox
        checked={settings.automation.enabled}
        label={t('automationEnabled')}
        testId="settings-automation"
        onChange={(enabled) => void updateSettings({ automation: { enabled } })}
      />
      <p className={styles.hint}>{t('automationHint')}</p>

      <h3 className={styles.heading}>{t('tools')}</h3>
      <p className={styles.hint}>{t('toolOptionsHint')}</p>
      <Button
        variant="secondary"
        data-testid="settings-reset-tools"
        disabled={!hasStoredToolOptions(settings)}
        onClick={() => void resetToolOptions(t('toolOptionsReset'))}
      >
        {t('resetToolOptions')}
      </Button>
    </Dialog>
  );
}

export const dialog = SettingsDialog;
