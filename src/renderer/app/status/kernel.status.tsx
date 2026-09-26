import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useJobs } from '../../state/jobStore';
import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import styles from './KernelStatus.module.css';
import type { StatusItem } from './types';

/** Short previews finish before this and never flash a progress bar. */
const SHOW_AFTER_MS = 400;
const ELAPSED_AFTER_MS = 10_000;

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/**
 * Nothing while idle. Progress and a cancel button while a job runs; a restart
 * button when the geometry process stopped or does not respond.
 */
function KernelState() {
  const { t } = useTranslation();
  const kernel = useJobs((state) => state.kernel);
  const jobs = useJobs((state) => state.jobs);
  const running = Object.values(jobs).sort((a, b) => a.startedAt - b.startedAt);
  const now = useNow(running.length > 0);
  const job = running.find((candidate) => now - candidate.startedAt >= SHOW_AFTER_MS);

  if (kernel.state === 'stopped' || kernel.state === 'unresponsive') {
    return (
      <span className={styles.state} data-testid="status-kernel">
        {t(kernel.state === 'stopped' ? 'status.kernelStopped' : 'status.kernelUnresponsive')}
        <Button variant="ghost" onClick={() => void window.m2c.kernel.restart()}>
          {t('actions.restart')}
        </Button>
      </span>
    );
  }
  if (kernel.state === 'starting')
    return (
      <span className={styles.state} data-testid="status-kernel">
        {t('status.kernelStarting')}
      </span>
    );
  if (!job) return null;

  const elapsed = now - job.startedAt;
  return (
    <span className={styles.state} data-testid="status-kernel">
      {job.stage ? t(`progress:${job.stage}`) : t('status.computing')}
      <ProgressBar fraction={job.fraction} label={t('status.computing')} />
      {elapsed > ELAPSED_AFTER_MS && t('status.elapsed', { seconds: Math.round(elapsed / 1000) })}
      <IconButton
        icon={X}
        label={t('status.cancel')}
        onClick={() => window.m2c.kernel.cancel(job.clientId)}
      />
    </span>
  );
}

export const statusItem: StatusItem = { order: 50, Component: KernelState };
