import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MeshReport } from '@shared/protocol/generated/mesh';

import { useFormatter } from '../../i18n/useFormatter';
import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { useDocument } from '../../state/documentStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import { toFailure } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from '../mesh-repair/scanEdit/ScanEdit.module.css';
import { repairableDefects } from './meshCondition';

type Inspection =
  | { status: 'computing' }
  | { status: 'ok'; report: MeshReport }
  | { status: 'error'; error: KernelFailure };

/** Size and condition of the scan; determined again after every change of the document. */
export function InfoPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const [settled, setSettled] = useState<{ revision: number; inspection: Inspection } | null>(null);

  useEffect(() => {
    if (revision === null) return;
    let current = true;
    kernel()
      .call('mesh.inspect', {})
      .result.then((report) => {
        if (current) setSettled({ revision, inspection: { status: 'ok', report } });
      })
      .catch((error: unknown) => {
        if (current && !isSilentFailure(error)) {
          setSettled({ revision, inspection: { status: 'error', error: toFailure(error) } });
        }
      });
    return () => {
      current = false;
    };
  }, [revision]);

  // A report of an older revision counts as still computing.
  const inspection: Inspection =
    settled !== null && settled.revision === revision
      ? settled.inspection
      : { status: 'computing' };
  const report = inspection.status === 'ok' ? inspection.report : null;
  const count = (value: number) => format.count(value);
  const yesNo = (value: boolean) => t(value ? 'meshInfo.yes' : 'meshInfo.no');

  return (
    <ToolPanel toolId="mesh-info" canCommit onCommit={close} onCancel={close}>
      <PanelSection title={t('meshInfo.scan')}>
        {inspection.status === 'computing' && (
          <p className={styles.hint}>{t('common:tool.computing')}</p>
        )}
        {inspection.status === 'error' && (
          <InlineMessage severity="error" details={inspection.error.details}>
            {describeError(inspection.error, t)}
          </InlineMessage>
        )}
        {report && (
          <>
            <PropertyValue label={t('meshInfo.faces')} value={count(report.faceCount)} />
            <PropertyValue label={t('meshInfo.vertices')} value={count(report.vertexCount)} />
            <PropertyValue
              label={t('meshInfo.size')}
              value={`${report.size.map((value) => format.number(value, 3)).join(' × ')} mm`}
            />
            <PropertyValue label={t('meshInfo.area')} value={format.area(report.area)} />
            <PropertyValue
              label={t('meshInfo.volume')}
              value={
                report.volume === null ? t('meshInfo.notClosed') : format.volume(report.volume)
              }
            />
            <PropertyValue
              label={t('meshInfo.noise')}
              value={report.noise === null ? t('meshInfo.unknown') : format.length(report.noise)}
            />
          </>
        )}
      </PanelSection>
      {report && (
        <PanelSection title={t('meshInfo.condition')}>
          <PropertyValue label={t('meshInfo.watertight')} value={yesNo(report.watertight)} />
          <PropertyValue label={t('meshInfo.holes')} value={count(report.boundaryLoops)} />
          <PropertyValue label={t('meshInfo.openEdges')} value={count(report.boundaryEdges)} />
          <PropertyValue
            label={t('meshInfo.nonManifoldEdges')}
            value={count(report.nonManifoldEdges)}
          />
          <PropertyValue
            label={t('meshInfo.inconsistentEdges')}
            value={count(report.inconsistentEdges)}
          />
          <PropertyValue label={t('meshInfo.parts')} value={count(report.components)} />
          <PropertyValue label={t('meshInfo.smallParts')} value={count(report.smallParts)} />
          <PropertyValue
            label={t('meshInfo.degenerateFaces')}
            value={count(report.degenerateFaces)}
          />
          <PropertyValue
            label={t('meshInfo.duplicateFaces')}
            value={count(report.duplicateFaces)}
          />
          <PropertyValue
            label={t('meshInfo.syntheticFaces')}
            value={count(report.syntheticFaces)}
          />
          {repairableDefects(report) && (
            <InlineMessage severity="info">{t('meshInfo.repairHint')}</InlineMessage>
          )}
          {report.smallParts > 0 && (
            <InlineMessage severity="info">{t('meshInfo.smallPartsHint')}</InlineMessage>
          )}
        </PanelSection>
      )}
    </ToolPanel>
  );
}
