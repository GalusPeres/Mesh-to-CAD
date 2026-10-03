import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ReferenceParams } from '@shared/protocol/generated/feature-reference';

import { featureNames } from '../../features/registry';
import { inputFeatures } from '../../features/reference/geometry';
import { describeError } from '../../kernel/describeError';
import { documentStore, useDocument } from '../../state/documentStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  DEFINITION_TYPES,
  type DefinitionType,
  EMPTY_REFERENCE,
  type ReferenceDraft,
  type SlotName,
  definitionOf,
  draftOf,
  nextEmptySlot,
  originInputs,
  slotsOf,
  withInput,
  withType,
} from './referenceDraft';
import styles from './ReferencePanel.module.css';
import { TOOL_ID, useInputPicking, useReferencePreview, useValueHandles } from './useReferenceTool';

const NONE = '';

function storedDraft(editTarget: string | null): ReferenceDraft {
  const feature = documentStore
    .getState()
    .snapshot?.document.features.find((item) => item.id === editTarget);
  if (feature?.type !== 'reference') return EMPTY_REFERENCE;
  return draftOf((feature.params as unknown as ReferenceParams).definition);
}

/**
 * Hilfsgeometrie: offset plane, plane through an axis at an angle, mid-plane of two
 * parallel planes, or axis where two planes meet. Inputs are picked from the list,
 * in the project tree or on construction geometry in the viewport.
 */
export function ReferencePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'common', 'features', 'panels']);
  const [draft, setDraft] = useState<ReferenceDraft>(() => storedDraft(editTarget));
  const [chosenSlot, setChosenSlot] = useState<SlotName | null>(null);
  const snapshot = useDocument((state) => state.snapshot);
  const features = useMemo(() => snapshot?.document.features ?? [], [snapshot]);
  const statuses = useMemo(() => snapshot?.status.features ?? {}, [snapshot]);
  const names = useMemo(() => featureNames(features, t), [features, t]);
  const { preview, commit } = useReferencePreview(draft, editTarget, close);

  const slots = slotsOf(draft.type);
  const activeSlot =
    chosenSlot && slots.some((slot) => slot.name === chosenSlot)
      ? chosenSlot
      : nextEmptySlot(draft);
  const candidates = useCallback(
    (kind: 'plane' | 'axis') => inputFeatures(features, statuses, kind, editTarget),
    [features, statuses, editTarget],
  );
  const accepts = useCallback(
    (featureId: string) => {
      const slot = slots.find((item) => item.name === activeSlot);
      return !!slot && candidates(slot.kind).some((feature) => feature.id === featureId);
    },
    [slots, activeSlot, candidates],
  );
  const assign = useCallback((slot: SlotName, input: string) => {
    setDraft((current) => withInput(current, slot, input));
    setChosenSlot(null);
  }, []);
  useInputPicking(activeSlot, accepts, assign);
  useValueHandles(draft, statuses, (value) =>
    setDraft((current) =>
      current.type === 'offsetPlane'
        ? { ...current, distance: value }
        : { ...current, angleDeg: value },
    ),
  );

  const label = (input: string) => names.get(input) ?? t(`tools:referenceGeometry.origin.${input}`);
  const status = preview.status === 'ok' ? preview.result.status : null;
  const failure = commit.error ?? (preview.status === 'error' ? preview.error : null);
  const featureError = status?.error ?? null;
  const editingName = editTarget ? names.get(editTarget) : undefined;
  const complete = definitionOf(draft) !== null;

  return (
    <ToolPanel
      toolId={TOOL_ID}
      editingName={editingName}
      canCommit={complete && preview.status === 'ok' && !featureError}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyRow label={t('referenceGeometry.definition')} htmlFor="reference-type">
          <Select<DefinitionType>
            id="reference-type"
            testId="reference-type"
            value={draft.type}
            options={DEFINITION_TYPES.map((type) => ({
              value: type,
              label: t(`referenceGeometry.types.${type}`),
            }))}
            onChange={(type) => setDraft(withType(draft, type))}
          />
        </PropertyRow>
        {slots.map((slot) => {
          const options = [
            ...originInputs(slot.kind),
            ...candidates(slot.kind).map((feature) => feature.id),
          ];
          return (
            <PropertyRow
              key={slot.name}
              label={t(`referenceGeometry.slots.${draft.type}.${slot.name}`)}
              htmlFor={`reference-${slot.name}`}
            >
              <div
                className={slot.name === activeSlot ? styles.active : undefined}
                onFocus={() => setChosenSlot(slot.name)}
              >
                <Select<string>
                  id={`reference-${slot.name}`}
                  testId={`reference-${slot.name}`}
                  value={draft.inputs[slot.name] ?? NONE}
                  options={[
                    { value: NONE, label: t('referenceGeometry.pick') },
                    ...options.map((input) => ({ value: input, label: label(input) })),
                  ]}
                  onChange={(input) => input !== NONE && assign(slot.name, input)}
                />
              </div>
            </PropertyRow>
          );
        })}
        {activeSlot && (
          <p className={styles.hint}>
            {t(
              `referenceGeometry.pickHint.${slots.find((slot) => slot.name === activeSlot)?.kind ?? 'plane'}`,
            )}
          </p>
        )}
      </PanelSection>
      {(draft.type === 'offsetPlane' || draft.type === 'planeThroughAxis') && (
        <PanelSection title={t('common:sections.parameters')}>
          {draft.type === 'offsetPlane' ? (
            <PropertyRow label={t('referenceGeometry.distance')} htmlFor="reference-distance">
              <NumberField
                id="reference-distance"
                value={draft.distance}
                kind="length"
                onCommit={(distance) => setDraft({ ...draft, distance })}
              />
            </PropertyRow>
          ) : (
            <PropertyRow label={t('referenceGeometry.angle')} htmlFor="reference-angle">
              <NumberField
                id="reference-angle"
                value={draft.angleDeg}
                kind="angle"
                step={15}
                onCommit={(angleDeg) => setDraft({ ...draft, angleDeg })}
              />
            </PropertyRow>
          )}
        </PanelSection>
      )}
      <PanelSection title={t('common:sections.result')}>
        {!complete && <p className={styles.hint}>{t('referenceGeometry.incomplete')}</p>}
        {complete && preview.status === 'computing' && (
          <p className={styles.hint}>{t('common:tool.computing')}</p>
        )}
        {complete && preview.status === 'ok' && !featureError && (
          <p data-testid="reference-result">
            {t(`referenceGeometry.created.${draft.type === 'axisFromPlanes' ? 'axis' : 'plane'}`)}
          </p>
        )}
        {featureError && (
          <InlineMessage severity="error" details={featureError.details ?? undefined}>
            {t(`errors:${featureError.code}`, featureError.params)}
          </InlineMessage>
        )}
        {failure && (
          <InlineMessage severity="error" details={failure.details}>
            {describeError(failure, t)}
          </InlineMessage>
        )}
      </PanelSection>
    </ToolPanel>
  );
}
