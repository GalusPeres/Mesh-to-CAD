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
import { availableBodies, defaultTarget } from '../extrude/solid/model';
import { useBodyLabel } from '../extrude/solid/SolidSections';
import { useCommit } from '../framework/hooks';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import { GroupList } from './GroupList';
import { chosenFeatures, defaultChecked, featureName, groupFeatures, needsBody } from './model';
import styles from './RecognizePanel.module.css';
import { type Recognition, useRecognition } from './useRecognition';
import { useRecognitionInfo } from './useRecognitionInfo';
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
  // Groups whose top edges stay sharp: the rounding measured on the scan is switched off.
  const [sharpChoice, setSharpChoice] = useState<{ result: unknown; groups: Set<number> }>();
  const sharp = useMemo(
    () => (sharpChoice?.result === result ? sharpChoice.groups : new Set<number>()),
    [sharpChoice, result],
  );
  const toggleRounding = useCallback(
    (group: number) => {
      const next = new Set(sharp);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      setSharpChoice({ result, groups: next });
    },
    [sharp, result],
  );
  const [hovered, setHovered] = useState<number | null>(null);
  useRecognitionOverlay(result, checked, hovered, { onToggle: toggle, onHover: setHovered });
  useRecognitionInfo(recognition, groups, checked, sharp);

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
    const roundEdges = chosen.filter((index) => {
      const group = result.features[index]?.group;
      return group !== undefined && !sharp.has(group);
    });
    await kernel().call('recognize.build', {
      scanKey,
      baseRevision,
      features: chosen,
      targetBody,
      names,
      roundEdges,
    }).result;
    close();
  }, [scanKey, result, chosen, targetBody, close, t, format, sharp]);
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
            sharp={sharp}
            hovered={hovered}
            onToggle={toggle}
            onToggleRounding={toggleRounding}
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
