import { useTranslation } from 'react-i18next';

import { useDocument } from '../../state/documentStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { documentFeatureNames } from '../names';
import styles from './ExportBodyList.module.css';
import type { PreflightState } from './usePreflight';

export interface ExportSurfaceListProps {
  preflight: PreflightState;
  /** Surfaces the user unticked (all others go along). */
  skipped: readonly string[];
  onChange: (skipped: string[]) => void;
}

/**
 * The open surfaces (open freeform nets) STEP can carry next to the bodies, one
 * checkbox each, ticked by default. An invalid surface cannot be chosen.
 */
export function ExportSurfaceList({ preflight, skipped, onChange }: ExportSurfaceListProps) {
  const { t } = useTranslation('inspection');
  const snapshot = useDocument((state) => state.snapshot);
  const names = documentFeatureNames(snapshot, t);
  if (preflight.status !== 'ok' || preflight.result.surfaces.length === 0) return null;
  return (
    <div role="group" aria-label={t('export.surfaces')} className={styles.list}>
      {preflight.result.surfaces.map((surface) => (
        <div key={surface.feature} className={styles.body}>
          <Checkbox
            label={`${names.get(surface.feature) ?? surface.feature} · ${t('export.faceCount', {
              count: surface.faces,
            })}`}
            checked={surface.valid && !skipped.includes(surface.feature)}
            disabled={!surface.valid}
            testId={`export-surface-${surface.feature}`}
            onChange={(checked) =>
              onChange(
                checked
                  ? skipped.filter((id) => id !== surface.feature)
                  : [...skipped, surface.feature],
              )
            }
          />
          {!surface.valid && (
            <InlineMessage severity="warning">{t('export.surfaceInvalid')}</InlineMessage>
          )}
        </div>
      ))}
    </div>
  );
}

/** Surfaces to export: the valid ones the user did not untick. */
export function exportableSurfaces(
  preflight: PreflightState,
  skipped: readonly string[],
): string[] {
  if (preflight.status !== 'ok') return [];
  return preflight.result.surfaces
    .filter((surface) => surface.valid && !skipped.includes(surface.feature))
    .map((surface) => surface.feature);
}
