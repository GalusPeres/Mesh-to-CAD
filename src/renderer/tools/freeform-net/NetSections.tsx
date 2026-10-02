import { useTranslation } from 'react-i18next';

import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { Button } from '../../ui/Button/Button';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import styles from './FreeformNetPanel.module.css';
import { HEATMAP_TOLERANCES } from './heatmap';
import type { NetEditor, NetEditorState } from './netEditor';

const KEY = 'tools:freeformNet';

export type NetSource = 'scan' | 'selection';
export type NetDensity = 'coarse' | 'medium' | 'fine';
export const DENSITY_QUADS: Record<NetDensity, number> = { coarse: 600, medium: 1500, fine: 4000 };
const DENSITIES: readonly NetDensity[] = ['coarse', 'medium', 'fine'];

interface GenerateProps {
  editor: NetEditor;
  state: NetEditorState;
  source: NetSource;
  density: NetDensity;
  selectionCount: number;
  onSource: (source: NetSource) => void;
  onDensity: (density: NetDensity) => void;
  onGenerate: () => void;
}

export function GenerateSection(props: GenerateProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const { state, source, selectionCount } = props;
  const selectionMissing = source === 'selection' && selectionCount < MIN_FIT_FACES;
  const generating = state.job?.kind === 'generate';
  return (
    <PanelSection title={t(`${KEY}.sections.net`)}>
      <PropertyRow label={t(`${KEY}.source`)}>
        <SegmentedControl<NetSource>
          value={source}
          ariaLabel={t(`${KEY}.source`)}
          segments={[
            { value: 'scan', label: t(`${KEY}.sources.scan`) },
            { value: 'selection', label: t(`${KEY}.sources.selection`) },
          ]}
          onChange={props.onSource}
        />
      </PropertyRow>
      {source === 'selection' && (
        <>
          <PropertyValue label={t(`${KEY}.triangles`)} value={format.count(selectionCount)} />
          {selectionMissing && (
            <p className={styles.hint}>
              {t(`${KEY}.selectionMissing`, { min: format.count(MIN_FIT_FACES) })}
            </p>
          )}
        </>
      )}
      <PropertyRow label={t(`${KEY}.density`)}>
        <SegmentedControl<NetDensity>
          value={props.density}
          ariaLabel={t(`${KEY}.density`)}
          segments={DENSITIES.map((value) => ({ value, label: t(`${KEY}.densities.${value}`) }))}
          onChange={props.onDensity}
        />
      </PropertyRow>
      {generating ? (
        <JobProgress editor={props.editor} state={state} />
      ) : (
        <Button
          variant={state.hasNet ? 'secondary' : 'primary'}
          className={styles.wide}
          disabled={selectionMissing || state.job !== null}
          data-testid="freeform-net-generate"
          onClick={props.onGenerate}
        >
          {t(`${KEY}.${state.hasNet ? 'regenerate' : 'generate'}`)}
        </Button>
      )}
    </PanelSection>
  );
}

function JobProgress({ editor, state }: { editor: NetEditor; state: NetEditorState }) {
  const { t } = useTranslation();
  const job = state.job;
  if (!job) return null;
  const label = job.stage ? t(`progress:${job.stage}`) : t(`${KEY}.jobs.${job.kind}`);
  return (
    <div className={styles.progress} data-testid="freeform-net-progress">
      <ProgressBar fraction={job.fraction} label={label} />
      <div className={styles.progressRow}>
        <span className={styles.hint}>{label}</span>
        <Button variant="ghost" onClick={() => editor.cancelJob()}>
          {t(`${KEY}.stop`)}
        </Button>
      </div>
    </div>
  );
}

export function EditSection({ editor, state }: { editor: NetEditor; state: NetEditorState }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const busy = state.job !== null;
  const scope = state.selected > 0 ? 'chosen' : 'all';
  const fitting = state.job?.kind === 'fit' || state.job?.kind === 'smooth';
  return (
    <PanelSection title={t(`${KEY}.sections.edit`)}>
      <p className={styles.hint}>{t(`${KEY}.editHint`)}</p>
      <Checkbox
        checked={state.snap}
        label={t(`${KEY}.snap`)}
        testId="freeform-net-snap"
        onChange={(snap) => editor.setSnap(snap)}
      />
      <PropertyValue
        label={t(`${KEY}.chosen`)}
        value={state.selected > 0 ? format.count(state.selected) : t(`${KEY}.none`)}
      />
      <div className={styles.buttons}>
        <Button
          disabled={busy}
          data-testid="freeform-net-fit"
          onClick={() => void editor.fit(false)}
        >
          {t(`${KEY}.fit.${scope}`)}
        </Button>
        <Button
          disabled={busy}
          data-testid="freeform-net-smooth"
          onClick={() => void editor.fit(true)}
        >
          {t(`${KEY}.smooth.${scope}`)}
        </Button>
      </div>
      <Button
        className={styles.wide}
        disabled={busy || state.selected < 3}
        data-testid="freeform-net-flatten"
        onClick={() => void editor.flatten()}
      >
        {t(`${KEY}.flatten`)}
      </Button>
      <div className={styles.buttons}>
        <Button variant="ghost" disabled={busy} onClick={() => editor.chooseAll()}>
          {t(`${KEY}.chooseAll`)}
        </Button>
        <Button
          variant="ghost"
          disabled={state.selected === 0}
          onClick={() => editor.choose([], 'replace')}
        >
          {t(`${KEY}.chooseNone`)}
        </Button>
      </div>
      {fitting && <JobProgress editor={editor} state={state} />}
    </PanelSection>
  );
}

export function DeviationSection({ editor, state }: { editor: NetEditor; state: NetEditorState }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const summary = state.summary;
  return (
    <PanelSection title={t(`${KEY}.sections.deviation`)}>
      <Checkbox
        checked={state.heatmap}
        label={t(`${KEY}.heatmap`)}
        testId="freeform-net-heatmap"
        onChange={(heatmap) => editor.setHeatmap(heatmap)}
      />
      <PropertyRow label={t(`${KEY}.scale`)}>
        <SegmentedControl<string>
          value={String(state.tolerance)}
          ariaLabel={t(`${KEY}.scale`)}
          segments={HEATMAP_TOLERANCES.map((value) => ({
            value: String(value),
            label: `±${format.number(value, value < 0.1 ? 2 : 1)}`,
          }))}
          onChange={(value) => editor.setTolerance(Number(value))}
        />
      </PropertyRow>
      <p className={styles.hint}>
        {t(`${KEY}.legend`, { tolerance: format.length(state.tolerance) })}
      </p>
      {summary && summary.rms !== null ? (
        <>
          {summary.withinTolerance !== null && (
            <PropertyValue
              label={t(`${KEY}.result.withinTolerance`)}
              value={format.percent(summary.withinTolerance)}
            />
          )}
          <PropertyValue label={t(`${KEY}.result.rms`)} value={format.length(summary.rms)} />
          {summary.p95 !== null && (
            <PropertyValue label={t(`${KEY}.result.p95`)} value={format.length(summary.p95)} />
          )}
          {summary.max !== null && (
            <PropertyValue label={t(`${KEY}.result.max`)} value={format.length(summary.max)} />
          )}
          {summary.measured < summary.total && (
            <p className={styles.hint}>
              {t(`${KEY}.result.unmeasured`, {
                share: format.percent(1 - summary.measured / summary.total),
              })}
            </p>
          )}
        </>
      ) : (
        <p className={styles.hint}>{t(`${KEY}.measuring`)}</p>
      )}
    </PanelSection>
  );
}

export function ResultSection({ state }: { state: NetEditorState }) {
  const { t } = useTranslation();
  const format = useFormatter();
  return (
    <PanelSection title={t('common:sections.result')}>
      <PropertyValue label={t(`${KEY}.result.quads`)} value={format.count(state.quads)} />
      <PropertyValue label={t(`${KEY}.result.points`)} value={format.count(state.controlPoints)} />
      <PropertyValue label={t(`${KEY}.result.irregular`)} value={format.count(state.irregular)} />
      <PropertyValue
        label={t(`${KEY}.result.shape`)}
        value={t(`${KEY}.result.${state.closed ? 'closedBody' : 'openSurface'}`)}
      />
      {!state.closed && <p className={styles.hint}>{t(`${KEY}.result.openHint`)}</p>}
    </PanelSection>
  );
}

export function ErrorMessage({ state }: { state: NetEditorState }) {
  const { t } = useTranslation();
  if (!state.error) return null;
  return (
    <InlineMessage severity="error" details={state.error.details}>
      {describeError(state.error, t)}
    </InlineMessage>
  );
}
