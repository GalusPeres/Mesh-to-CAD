import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RecognizeParams } from '@shared/protocol/generated/recognize';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { currentRevision, useDocument } from '../../state/documentStore';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { RECOGNITION_COLORS } from '../../viewport/palette';
import { availableBodies, defaultTarget } from '../extrude/solid/model';
import { useBodyLabel } from '../extrude/solid/SolidSections';
import { useCommit } from '../framework/hooks';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  type FeatureGroup,
  chosenFeatures,
  defaultChecked,
  featureName,
  groupFeatures,
  needsBody,
} from './model';
import styles from './RecognizePanel.module.css';
import { type Recognition, useRecognition } from './useRecognition';
import { useRecognitionOverlay } from './useRecognitionOverlay';

const KEY = 'tools:recognize';
const NEW_BODIES = '';

/**
 * Formen erkennen: reads the aligned scan like a designer (flat faces, and on them
 * buttons, pockets, slots, ring segments, holes and free outlines of lines and arcs)
 * and builds the checked ones as a plane, sketches and extrusions in one step.
 */
export function RecognizePanel({ close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const scanKey = snapshot?.document.scan?.key ?? null;
  // The recognition runs on the aligned scan: a new alignment runs it again.
  const transform = snapshot?.scene.scan?.transform.join(',') ?? '';
  const params = useMemo<RecognizeParams | null>(
    () => (scanKey ? { scanKey } : null),
    // `transform` changes the result although the parameters stay the same.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scanKey, transform],
  );
  const { recognition, cancel, restart } = useRecognition(params);
  const result = recognition.status === 'ok' ? recognition.result : null;
  const groups = useMemo(() => (result ? groupFeatures(result) : []), [result]);

  const [choice, setChoice] = useState<{ result: unknown; checked: Set<number> } | null>(null);
  const checked = useMemo(
    () => (choice && choice.result === result ? choice.checked : defaultChecked(groups)),
    [choice, result, groups],
  );
  const setChecked = useCallback(
    (update: (current: Set<number>) => Set<number>) =>
      setChoice({ result, checked: update(new Set(checked)) }),
    [result, checked],
  );
  const toggle = useCallback(
    (group: number) =>
      setChecked((current) => {
        if (current.has(group)) current.delete(group);
        else current.add(group);
        return current;
      }),
    [setChecked],
  );
  const [hovered, setHovered] = useState<number | null>(null);
  useRecognitionOverlay(result, checked, hovered, { onToggle: toggle, onHover: setHovered });

  const bodies = useMemo(() => (snapshot ? availableBodies(snapshot, null) : []), [snapshot]);
  const bodyLabel = useBodyLabel();
  const [target, setTarget] = useState<string>(() => defaultTarget(bodies) ?? NEW_BODIES);
  const targetBody = bodies.some((body) => body.id === target) ? target : null;
  const chosen = chosenFeatures(groups, checked);
  const pocketsChosen = needsBody(groups, checked);
  const bossesChosen = groups.some((group) => checked.has(group.id) && group.role === 'boss');

  const format = useFormatter();
  const build = useCallback(async () => {
    const baseRevision = currentRevision();
    if (!scanKey || !result || baseRevision === null || chosen.length === 0) return;
    // The extrusions are named like their shapes, in the user's language.
    const names = chosen.map((index) => {
      const feature = result.features[index];
      return feature ? featureName(feature, t(`${KEY}.shapeNames.${feature.shape}`), format) : '';
    });
    await kernel().call('recognize.build', {
      scanKey,
      baseRevision,
      features: chosen,
      targetBody,
      names,
    }).result;
    close();
  }, [scanKey, result, chosen, targetBody, close, t, format]);
  const commit = useCommit(build);
  const canCommit = result !== null && (targetBody !== null ? chosen.length > 0 : bossesChosen);

  return (
    <ToolPanel
      toolId="recognize"
      canCommit={canCommit}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t(`${KEY}.found`)}>
        <RecognitionState recognition={recognition} onCancel={cancel} onRestart={restart} />
        {result && (
          <GroupList
            groups={groups}
            checked={checked}
            hovered={hovered}
            onToggle={toggle}
            onHover={setHovered}
            onAll={(all) => setChecked(() => (all ? defaultChecked(groups) : new Set<number>()))}
          />
        )}
      </PanelSection>
      {result && groups.length > 0 && (
        <PanelSection title={t(`${KEY}.target`)}>
          <PropertyRow label={t(`${KEY}.targetBody`)}>
            <Select<string>
              value={targetBody ?? NEW_BODIES}
              ariaLabel={t(`${KEY}.targetBody`)}
              testId="recognize-target"
              options={[
                { value: NEW_BODIES, label: t(`${KEY}.newBodies`) },
                ...bodies.map((body) => ({ value: body.id, label: bodyLabel(body) })),
              ]}
              onChange={setTarget}
            />
          </PropertyRow>
          {targetBody === null && pocketsChosen && (
            <InlineMessage severity="info">{t(`${KEY}.needsBody`)}</InlineMessage>
          )}
          {commit.error && (
            <InlineMessage severity="error" details={commit.error.details}>
              {describeError(commit.error, t)}
            </InlineMessage>
          )}
        </PanelSection>
      )}
    </ToolPanel>
  );
}

interface RecognitionStateProps {
  recognition: Recognition;
  onCancel: () => void;
  onRestart: () => void;
}

function RecognitionState({ recognition, onCancel, onRestart }: RecognitionStateProps) {
  const { t } = useTranslation();
  switch (recognition.status) {
    case 'idle':
      return <p className={styles.hint}>{t('errors:regions.noScan')}</p>;
    case 'computing': {
      const label = recognition.stage ? t(`progress:${recognition.stage}`) : t(`${KEY}.computing`);
      return (
        <div className={styles.progress} data-testid="recognize-progress">
          <ProgressBar fraction={recognition.fraction} label={label} />
          <div className={styles.progressRow}>
            <span className={styles.hint}>{label}</span>
            <Button variant="ghost" data-testid="recognize-stop" onClick={onCancel}>
              {t(`${KEY}.stop`)}
            </Button>
          </div>
        </div>
      );
    }
    case 'cancelled':
      return (
        <div className={styles.progressRow}>
          <span className={styles.hint}>{t(`${KEY}.stopped`)}</span>
          <Button data-testid="recognize-restart" onClick={onRestart}>
            {t(`${KEY}.compute`)}
          </Button>
        </div>
      );
    case 'error':
      return (
        <InlineMessage severity="error" details={recognition.error.details}>
          {describeError(recognition.error, t)}
        </InlineMessage>
      );
    case 'ok':
      return recognition.result.features.length === 0 ? (
        <p className={styles.hint}>{t(`${KEY}.nothingFound`)}</p>
      ) : null;
  }
}

interface GroupListProps {
  groups: readonly FeatureGroup[];
  checked: ReadonlySet<number>;
  hovered: number | null;
  onToggle: (group: number) => void;
  onHover: (group: number | null) => void;
  onAll: (all: boolean) => void;
}

function GroupList({ groups, checked, hovered, onToggle, onHover, onAll }: GroupListProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  if (groups.length === 0) return null;
  const count = groups.reduce((sum, group) => sum + group.indices.length, 0);
  return (
    <>
      <div className={styles.listHeader}>
        <span>{t(`${KEY}.featureCount`, { count, formatted: format.count(count) })}</span>
        <span className={styles.listActions}>
          <Button variant="ghost" data-testid="recognize-all" onClick={() => onAll(true)}>
            {t(`${KEY}.all`)}
          </Button>
          <Button variant="ghost" data-testid="recognize-none" onClick={() => onAll(false)}>
            {t(`${KEY}.none`)}
          </Button>
        </span>
      </div>
      <ul className={styles.list} data-testid="recognize-groups" onMouseLeave={() => onHover(null)}>
        {groups.map((group) => (
          <GroupRow
            key={group.id}
            group={group}
            checked={checked.has(group.id)}
            hovered={hovered === group.id}
            onToggle={onToggle}
            onHover={onHover}
          />
        ))}
      </ul>
    </>
  );
}

interface GroupRowProps {
  group: FeatureGroup;
  checked: boolean;
  hovered: boolean;
  onToggle: (group: number) => void;
  onHover: (group: number | null) => void;
}

function GroupRow({ group, checked, hovered, onToggle, onHover }: GroupRowProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const { feature } = group;
  const color = RECOGNITION_COLORS[group.role];
  const amount = format.length(feature.height, { decimals: 2 });
  const details = [
    t(`${KEY}.roles.${group.role}`),
    group.role === 'hole'
      ? t(`${KEY}.through`)
      : t(`${KEY}.${group.role === 'boss' ? 'height' : 'depth'}`, { value: amount }),
    feature.top === 'domed' ? t(`${KEY}.domed`) : null,
    group.nested ? t(`${KEY}.nested`) : null,
  ].filter(Boolean);
  const name = featureName(feature, t(`${KEY}.shapeNames.${feature.shape}`), format);
  return (
    <li
      className={`${styles.row} ${hovered ? styles.hovered : ''}`}
      data-testid={`recognize-group-${group.id}`}
      onMouseEnter={() => onHover(group.id)}
    >
      <input
        type="checkbox"
        className={styles.box}
        checked={checked}
        aria-label={name}
        onChange={() => onToggle(group.id)}
      />
      <span className={styles.swatch} style={{ background: color }} aria-hidden />
      <span className={styles.text}>
        <span className={styles.name}>
          {group.indices.length > 1 && (
            <span className={styles.count}>{group.indices.length} × </span>
          )}
          {name}
        </span>
        <span className={styles.details}>{details.join(' · ')}</span>
      </span>
    </li>
  );
}
