import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AppInfo } from '@shared/bridge';
import type { SystemInfoResult } from '@shared/protocol/generated/system';

import { openHelp } from '../help/openHelp';
import { kernel } from '../kernel/kernel';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { PropertyValue } from '../ui/PropertyRow/PropertyRow';
import { closeDialog, useOpenDialog } from './appDialogStore';
import styles from './SettingsDialog.module.css';

interface Versions {
  app: AppInfo | null;
  kernel: SystemInfoResult | null;
}

/** Load both version sets; the computing process may be stopped, which leaves its rows empty. */
async function loadVersions(): Promise<Versions> {
  const [app, kernelInfo] = await Promise.allSettled([
    window.m2c.app.info(),
    kernel().call('system.info', {}).result,
  ]);
  return {
    app: app.status === 'fulfilled' ? app.value : null,
    kernel: kernelInfo.status === 'fulfilled' ? kernelInfo.value : null,
  };
}

/** Versions of every component, the licences and where the logs are (docs/DESIGN.md 5.9). */
function AboutDialog() {
  const { t } = useTranslation(['settings', 'common']);
  const open = useOpenDialog() === 'about';
  const [versions, setVersions] = useState<Versions>({ app: null, kernel: null });

  useEffect(() => {
    if (!open) return;
    let current = true;
    void loadVersions().then((loaded) => {
      if (current) setVersions(loaded);
    });
    return () => {
      current = false;
    };
  }, [open]);

  const unknown = t('about.unavailable');
  const { app, kernel: kernelInfo } = versions;
  const rows: [string, string | undefined][] = [
    ['about.version', app?.version],
    ['about.kernel', kernelInfo?.kernelVersion],
    ['about.occt', kernelInfo?.occtVersion],
    ['about.python', kernelInfo?.pythonVersion],
    ['about.electron', app?.electron],
    ['about.chrome', app?.chrome],
    ['about.node', app?.node],
    ['about.platform', app?.platform],
  ];

  return (
    <Dialog
      open={open}
      title={t('common:commands.about')}
      onOpenChange={(next) => {
        if (!next) closeDialog();
      }}
      footer={
        <Button variant="primary" data-testid="about-close" onClick={closeDialog}>
          {t('common:actions.close')}
        </Button>
      }
    >
      <p className={styles.hint}>{t('about.description')}</p>
      <div className={styles.values} data-testid="about-versions">
        {rows.map(([key, value]) => (
          <PropertyValue key={key} label={t(key)} value={value ?? unknown} />
        ))}
      </div>
      <h3 className={styles.heading}>{t('about.licenses')}</h3>
      <p className={styles.hint}>{t('about.licenseText')}</p>
      <div className={styles.actions}>
        <Button
          variant="secondary"
          data-testid="about-licenses"
          onClick={() => openHelp('licenses')}
        >
          {t('about.showLicenses')}
        </Button>
      </div>
      <h3 className={styles.heading}>{t('about.logs')}</h3>
      <p className={styles.path} data-testid="about-log-folder">
        {app?.logDirectory ?? unknown}
      </p>
    </Dialog>
  );
}

export const dialog = AboutDialog;
