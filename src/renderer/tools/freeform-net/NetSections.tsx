// The freeform-net panel's sections, kept short: controls as icon buttons with their
// explanation in the tooltip, numbers instead of sentences. What the pointer does is
// told in the status bar (freeformNet.status.tsx), not here.

import {
  ArrowUpToLine,
  Magnet,
  Palette,
  RectangleHorizontal,
  Square,
  SquarePlus,
  Waves,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import styles from './FreeformNetPanel.module.css';
import { HEATMAP_TOLERANCES } from './heatmap';
import type { NetEditor, NetEditorState } from './netEditor';
import type { FaceMode } from './netFacePlacement';
import { PointOptions, StrengthOptions } from './NetPointOptions';
import { referenceCount, usePushReferences } from './netReferences';

const KEY = 'tools:freeformNet';

export type NetSource = 'scan' | 'selection';
export type NetDensity = 'coarse' | 'medium' | 'fine';
export const DENSITY_QUADS: Record<NetDensity, number> = { coarse: 600, medium: 1500, fine: 4000 };
const DENSITIES: readonly NetDensity[] = ['coarse', 'medium', 'fine'];

interface SectionProps {
  editor: NetEditor;
  state: NetEditorState;
}

interface GenerateProps extends SectionProps {
  source: NetSource;
  density: NetDensity;
  selectionCount: number;
  onSource: (source: NetSource) => void;
  onDensity: (density: NetDensity) => void;
  onGenerate: () => void;
}

/** Auto net: over the whole scan or the selected triangles, in one of three densities. */
export function GenerateSection(props: GenerateProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const { state, source } = props;
  const selectionMissing = source === 'selection' && props.selectionCount < MIN_FIT_FACES;
  return (
    <PanelSection title={t(`${KEY}.sections.net`)}>
      <SegmentedControl<NetSource>
        value={source}
        ariaLabel={t(`${KEY}.source`)}
        segments={[
          { value: 'scan', label: t(`${KEY}.sources.scan`) },
          { value: 'selection', label: t(`${KEY}.sources.selection`) },
        ]}
        onChange={props.onSource}
      />
      <div className={styles.row}>
        <SegmentedControl<NetDensity>
          value={props.density}
          ariaLabel={t(`${KEY}.density`)}
          segments={DENSITIES.map((value) => ({ value, label: t(`${KEY}.densities.${value}`) }))}
          onChange={props.onDensity}
        />
        <Button
          variant={state.hasNet ? 'secondary' : 'primary'}
          disabled={selectionMissing || state.job !== null}
          title={
            selectionMissing
              ? t(`${KEY}.selectionMissing`, { min: format.count(MIN_FIT_FACES) })
              : undefined
          }
          data-testid="freeform-net-generate"
          onClick={props.onGenerate}
        >
          {t(`${KEY}.${state.hasNet ? 'regenerate' : 'generate'}`)}
        </Button>
      </div>
      {state.job?.kind === 'generate' && <JobProgress {...props} />}
    </PanelSection>
  );
}

function JobProgress({ editor, state }: SectionProps) {
  const { t } = useTranslation();
  const job = state.job;
  if (!job) return null;
  const label = job.stage ? t(`progress:${job.stage}`) : t(`${KEY}.jobs.${job.kind}`);
  return (
    <div className={styles.row} data-testid="freeform-net-progress">
      <ProgressBar fraction={job.fraction} label={label} />
      <Button variant="ghost" onClick={() => editor.cancelJob()}>
        {t(`${KEY}.stop`)}
      </Button>
    </div>
  );
}

/** Building and shaping by hand: the face button, a row of icon tools, the choice as one line. */
export function ToolsSection({ editor, state }: SectionProps) {
  const { t } = useTranslation();
  const busy = state.job !== null;
  const scope = state.selected > 0 ? 'chosen' : 'all';
  const tool = (name: string) => ({
    label: t(`${KEY}.tools.${name}.label`),
    description: t(`${KEY}.tools.${name}.description`),
  });
  const fitting =
    state.job?.kind === 'fit' || state.job?.kind === 'smooth' || state.job?.kind === 'push';
  return (
    <PanelSection title={t(`${KEY}.sections.build`)}>
      <div className={styles.toolbar}>
        <FaceButton editor={editor} state={state} mode="quad" />
        <FaceButton editor={editor} state={state} mode="rectangle" />
      </div>
      <div className={styles.icons}>
        <IconButton
          icon={Magnet}
          {...tool(`fit.${scope}`)}
          disabled={busy || !state.hasNet}
          data-testid="freeform-net-fit"
          onClick={() => void editor.shape.fit(false)}
        />
        <IconButton
          icon={Waves}
          {...tool(`smooth.${scope}`)}
          disabled={busy || !state.hasNet}
          data-testid="freeform-net-smooth"
          onClick={() => void editor.shape.fit(true)}
        />
        <IconButton
          icon={Square}
          {...tool('flatten')}
          disabled={busy || state.selected < 3}
          data-testid="freeform-net-flatten"
          onClick={() => void editor.shape.flatten()}
        />
        <PushButton editor={editor} state={state} />
        <span className={styles.separator} aria-hidden />
        <PointOptions editor={editor} state={state} />
      </div>
      <StrengthOptions editor={editor} state={state} />
      <ChoiceFacts state={state} />
      {fitting && <JobProgress editor={editor} state={state} />}
    </PanelSection>
  );
}

/** The choice as one line: chosen edges or points, and the pinned points. */
function ChoiceFacts({ state }: { state: NetEditorState }) {
  const { t } = useTranslation();
  const facts = [
    state.chosenEdges > 0
      ? t(`${KEY}.chosenEdges`, { count: state.chosenEdges })
      : state.selected > 0 && t(`${KEY}.chosenPoints`, { count: state.selected }),
    state.pinned > 0 && t(`${KEY}.pinnedPoints`, { count: state.pinned }),
    state.pushed &&
      (state.pushed.moved > 0
        ? `${t(`${KEY}.pushed`, { count: state.pushed.moved })} · ${t(`${KEY}.pushedFaces`, { count: state.pushed.faces })}`
        : t(`${KEY}.nothingPushed`)),
  ].filter(Boolean);
  if (facts.length === 0) return null;
  return (
    <p className={styles.facts} data-testid="freeform-net-choice">
      {facts.join(' · ')}
    </p>
  );
}

/** Push the net's open border past the shown planes and bodies (before trimming). */
function PushButton({ editor, state }: SectionProps) {
  const { t } = useTranslation();
  const references = usePushReferences();
  return (
    <IconButton
      icon={ArrowUpToLine}
      label={t(`${KEY}.tools.push.label`)}
      description={t(`${KEY}.tools.push.description`)}
      disabled={state.job !== null || !state.hasNet || referenceCount(references) === 0}
      data-testid="freeform-net-push"
      onClick={() => void editor.shape.pushPast(references)}
    />
  );
}

/** Start (or stop) placing a face: four corners, or a rectangle from two. */
function FaceButton({ editor, state, mode }: SectionProps & { mode: FaceMode }) {
  const { t } = useTranslation();
  const name = mode === 'quad' ? 'face' : 'rectangle';
  const active = state.facing && state.faceMode === mode;
  return (
    <Button
      variant={active ? 'primary' : 'secondary'}
      className={styles.labelled}
      disabled={state.job !== null}
      aria-pressed={active}
      title={t(`${KEY}.tools.${name}.description`)}
      data-testid={`freeform-net-add-${name}`}
      onClick={() => editor.build.setFacing(!active, mode)}
    >
      {mode === 'quad' ? (
        <SquarePlus size={16} aria-hidden />
      ) : (
        <RectangleHorizontal size={16} aria-hidden />
      )}
      {t(`${KEY}.tools.${name}.label`)}
    </Button>
  );
}

/** Deviation from the scan: heatmap on/off, colour scale, and the share within it. */
export function DeviationSection({ editor, state }: SectionProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const summary = state.summary;
  return (
    <PanelSection title={t(`${KEY}.sections.deviation`)}>
      <div className={styles.row}>
        <IconButton
          icon={Palette}
          label={t(`${KEY}.heatmap`)}
          description={t(`${KEY}.legend`)}
          pressed={state.heatmap}
          data-testid="freeform-net-heatmap"
          onClick={() => editor.setHeatmap(!state.heatmap)}
        />
        <SegmentedControl<string>
          value={String(state.tolerance)}
          ariaLabel={t(`${KEY}.scale`)}
          segments={HEATMAP_TOLERANCES.map((value) => ({
            value: String(value),
            label: `±${format.number(value, value < 0.1 ? 2 : 1)}`,
          }))}
          onChange={(value) => editor.setTolerance(Number(value))}
        />
      </div>
      {summary && summary.rms !== null ? (
        <div className={styles.score} data-testid="freeform-net-score">
          <span className={styles.big}>
            {summary.withinTolerance !== null ? format.percent(summary.withinTolerance) : '–'}
          </span>
          <span className={styles.facts}>
            {t(`${KEY}.score`, {
              rms: format.length(summary.rms),
              max: format.length(summary.max ?? summary.rms),
            })}
          </span>
        </div>
      ) : (
        <p className={styles.facts}>{t(`${KEY}.measuring`)}</p>
      )}
      <NetFacts state={state} />
    </PanelSection>
  );
}

/** One line about the result: quads, CAD faces, irregular points, surface or body. */
function NetFacts({ state }: { state: NetEditorState }) {
  const { t } = useTranslation();
  return (
    <p className={styles.facts} data-testid="freeform-net-facts">
      {t(`${KEY}.quads`, { count: state.quads })}
      {' · '}
      {t(`${KEY}.faces`, { count: state.faces })}
      {state.irregular > 0 && (
        <span className={styles.warning} title={t(`${KEY}.irregularHint`)}>
          {' · '}
          {t(`${KEY}.irregular`, { count: state.irregular })}
        </span>
      )}
      {' · '}
      {t(`${KEY}.${state.closed ? 'closedBody' : 'openSurface'}`)}
    </p>
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
