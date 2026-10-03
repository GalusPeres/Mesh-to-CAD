import { RotateCcw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PieceChoice, TrimSolidParams } from '@shared/protocol/generated/feature-trim-solid';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { IconButton } from '../../ui/IconButton/IconButton';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import { ORIGIN_PLANES, availableBodies, storedParams } from '../extrude/solid/model';
import { SolidResult, useBodyLabel } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';
import styles from './TrimSolidPanel.module.css';
import {
  type InputKind,
  type TrimInputs,
  initialInputs,
  inputCount,
  toggleInput,
  trimCandidates,
} from './inputs';
import { usePiecePicking } from './usePiecePicking';

const KEY = 'tools:trimSolid';
const KINDS: readonly InputKind[] = ['surfaces', 'planes', 'bodies'];
const isOrigin = (id: string) => (ORIGIN_PLANES as readonly string[]).includes(id);

/**
 * Zuschneiden (QuickSurface's Trim): nets, planes and bodies cut each other; the pieces
 * inside the scan form one body, and a click on a piece keeps or removes it.
 */
export function TrimSolidPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const bodyLabel = useBodyLabel();
  const stored = useMemo(
    () => storedParams<TrimSolidParams>(snapshot, editTarget, 'trimSolid'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const candidates = useMemo(
    () =>
      snapshot ? trimCandidates(snapshot, editTarget) : { surfaces: [], planes: [], bodies: [] },
    [snapshot, editTarget],
  );
  const bodyNumbers = useMemo(
    () => new Map((snapshot ? availableBodies(snapshot, editTarget) : []).map((b) => [b.id, b])),
    [snapshot, editTarget],
  );

  const [inputs, setInputs] = useState<TrimInputs>(
    () => stored ?? initialInputs(candidates, objectSelectionStore.getState().selected),
  );
  const [pieces, setPieces] = useState<PieceChoice[]>(stored?.pieces ?? []);

  const params = useMemo<TrimSolidParams | null>(
    () => (inputCount(inputs) > 0 ? { ...inputs, pieces } : null),
    [inputs, pieces],
  );
  const { preview, commit, deviation, previewOk } = useSolidFeature(
    'trim-solid',
    'trimSolid',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );
  const featureId = preview.status === 'ok' ? preview.result.featureId : null;
  usePiecePicking({ body: inputs.bodies[0] ?? featureId, feature: featureId }, (choice) =>
    setPieces((current) => [...current, choice]),
  );

  const stats = preview.status === 'ok' ? preview.result.status?.stats : undefined;
  const label = (kind: InputKind, id: string) => {
    if (kind === 'bodies') {
      const body = bodyNumbers.get(id);
      return body ? bodyLabel(body) : id;
    }
    if (isOrigin(id)) return t(`tools:extrude.solid.originPlanes.${id}`);
    return names.get(id) ?? id;
  };
  const choose = (kind: InputKind) => (id: string) =>
    setInputs((current) => toggleInput(current, kind, id, candidates[kind]));

  return (
    <ToolPanel
      toolId="trim-solid"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {candidates.surfaces.length + candidates.bodies.length === 0 && (
          <InlineMessage severity="info">{t(`${KEY}.nothing`)}</InlineMessage>
        )}
        {KINDS.map((kind) =>
          candidates[kind].map((id) => (
            <Checkbox
              key={`${kind}:${id}`}
              checked={inputs[kind].includes(id)}
              label={label(kind, id)}
              testId={`trim-solid-${kind}-${id}`}
              onChange={() => choose(kind)(id)}
            />
          )),
        )}
      </PanelSection>
      <PanelSection title={t(`${KEY}.pieces`)}>
        <div className={styles.row}>
          <span className={styles.facts} data-testid="trim-solid-pieces">
            {stats?.pieces != null
              ? t(`${KEY}.kept`, { count: stats.pieces, kept: stats.kept ?? 0 })
              : t(`${KEY}.noPieces`)}
          </span>
          <IconButton
            icon={RotateCcw}
            label={t(`${KEY}.automatic.label`)}
            description={t(`${KEY}.automatic.description`)}
            disabled={pieces.length === 0}
            data-testid="trim-solid-automatic"
            onClick={() => setPieces([])}
          />
        </div>
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} deviation={deviation} />
    </ToolPanel>
  );
}
