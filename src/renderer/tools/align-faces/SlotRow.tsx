import { TriangleAlert, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { InputFit } from '@shared/protocol/generated/alignment-inputs';
import type { InputRole } from '@shared/protocol/generated/alignment-params';

import { useFormatter } from '../../i18n/useFormatter';
import { classNames } from '../../lib/classNames';
import { IconButton } from '../../ui/IconButton/IconButton';
import styles from './AlignFacesPanel.module.css';
import type { SlotInput, SlotProblem } from './slots';

const KEY = 'tools:alignFaces';

interface SlotRowProps {
  role: InputRole;
  input: SlotInput | null;
  /** Display name of the input ("Ebene 1", "Bereich 3"). */
  name: string | null;
  active: boolean;
  problem: SlotProblem | undefined;
  fit: InputFit | undefined;
  onActivate: () => void;
  onClear: () => void;
}

/** One 3-2-1 input: its role, what it holds, how well it was fitted and what is wrong. */
export function SlotRow({
  role,
  input,
  name,
  active,
  problem,
  fit,
  onActivate,
  onClear,
}: SlotRowProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const roleLabel = t(`${KEY}.roles.${role}`);
  const value = name ?? t(`${KEY}.empty.${role === 'tertiary' ? 'optional' : 'required'}`);
  return (
    <div className={classNames(styles.slot, active && styles.active)}>
      <button
        type="button"
        className={styles.body}
        aria-pressed={active}
        data-testid={`align-slot-${role}`}
        onClick={onActivate}
      >
        <span className={styles.role}>{roleLabel}</span>
        <span className={classNames(styles.value, !input && styles.empty)}>{value}</span>
        {fit && (
          <span className={styles.fit}>
            {fit.rms === null
              ? t(`${KEY}.kinds.${fit.kind}`, { defaultValue: fit.kind })
              : t(`${KEY}.fit`, {
                  kind: t(`${KEY}.kinds.${fit.kind}`, { defaultValue: fit.kind }),
                  rms: format.length(fit.rms),
                  faces: format.count(fit.faceCount),
                })}
          </span>
        )}
        {problem && problem !== 'missing' && (
          <span className={styles.problem}>
            <TriangleAlert size={12} aria-hidden className={styles.problemIcon} />
            <span>{t(`${KEY}.problems.${problem}`)}</span>
          </span>
        )}
      </button>
      {input && (
        <IconButton icon={X} label={t(`${KEY}.clear`, { role: roleLabel })} onClick={onClear} />
      )}
    </div>
  );
}
