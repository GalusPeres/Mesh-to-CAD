import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { InputRole } from '@shared/protocol/generated/alignment-params';
import type { AlignmentAdjust, Document } from '@shared/protocol/generated/document-model';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { regionName } from '../../panels/treeModel';
import { selectedFaces, useSelectedFaceCount } from '../../selection/api';
import { documentStore, useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { Button } from '../../ui/Button/Button';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { AdjustControls, AlignmentResult } from '../align-auto/AlignmentSections';
import { type AdjustAction, applyAdjust } from '../align-auto/adjust';
import { commitAlignment, committedAlignment, initialAdjust } from '../align-auto/alignmentActions';
import { useFrameOverlay } from '../align-auto/useFrameOverlay';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit, usePreview } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './AlignFacesPanel.module.css';
import { SlotRow } from './SlotRow';
import {
  EMPTY_SLOTS,
  ROLES,
  type SlotInput,
  type Slots,
  assignInput,
  isComplete,
  previewSlot,
  slotProblems,
  slotsFromObjects,
  slotsFromParams,
} from './slots';
import { useSlotPicking } from './useSlotPicking';
import { useUndoableDraft } from './useUndoableDraft';

const KEY = 'tools:alignFaces';

interface Draft {
  slots: Slots;
  adjust: AlignmentAdjust;
}

function initialDraft(editTarget: string | null): Draft {
  const alignment = committedAlignment();
  const document = documentStore.getState().snapshot?.document;
  let slots = EMPTY_SLOTS;
  if (editTarget === 'alignment' && alignment?.method === 'faces') {
    slots = slotsFromParams(alignment.params);
  } else if (document) {
    slots = slotsFromObjects(objectSelectionStore.getState().selected, document);
  }
  return { slots, adjust: initialAdjust('faces', editTarget) };
}

function useInputName(document: Document | null): (input: SlotInput | null) => string | null {
  const { t } = useTranslation();
  const format = useFormatter();
  const names = useMemo(() => featureNames(document?.features ?? [], t), [document, t]);
  return (input) => {
    if (!input) return null;
    switch (input.type) {
      case 'feature':
        return names.get(input.feature) ?? input.feature;
      case 'region': {
        const region = document?.regions.items.find((item) => item.id === input.region);
        return region ? regionName(region, t) : input.region;
      }
      case 'faces':
        return t(`${KEY}.storedFaces`);
      case 'selection':
        return t(`${KEY}.selection`, {
          count: input.faces.length,
          formatted: format.count(input.faces.length),
        });
    }
  };
}

/**
 * 3-2-1 alignment: the primary datum gives Z, the secondary X or Y, the optional
 * tertiary the origin. Inputs are fit features, reference geometry, regions or the
 * working selection, picked in the tree or the viewport into the active slot.
 */
export function AlignFacesPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const document = snapshot?.document ?? null;
  const scanKey = document?.scan?.key ?? null;
  const [draft, updateDraft] = useUndoableDraft(() => initialDraft(editTarget));
  const [active, setActive] = useState<InputRole>(
    () => ROLES.find((role) => !draft.slots[role]) ?? 'primary',
  );
  const selectionCount = useSelectedFaceCount();
  const inputName = useInputName(document);

  const place = useCallback(
    (role: InputRole, input: SlotInput | null) => {
      const placed = assignInput(draft.slots, role, input);
      updateDraft((value) => ({ ...value, slots: placed.slots }));
      setActive(placed.next);
    },
    [draft.slots, updateDraft],
  );
  useSlotPicking((input) => place(active, input));

  const problems = useMemo(
    () => (document ? slotProblems(draft.slots, document, scanKey) : {}),
    [draft.slots, document, scanKey],
  );
  const revision = snapshot?.revision ?? null;
  const params = useMemo(() => {
    if (!isComplete(problems) || revision === null) return null;
    return {
      method: 'faces' as const,
      primary: previewSlot(draft.slots.primary),
      secondary: previewSlot(draft.slots.secondary),
      tertiary: previewSlot(draft.slots.tertiary),
      adjust: draft.adjust,
    };
  }, [problems, revision, draft]);
  const preview = usePreview('alignment.preview', params, 'align-faces');
  const result = preview.status === 'ok' ? preview.result : null;
  useFrameOverlay(result?.matrix ?? null);

  const apply = useCallback(async () => {
    if (!result) return;
    await commitAlignment('faces', result.params, draft.adjust);
    close();
  }, [result, draft.adjust, close]);
  const commit = useCommit(apply);

  const takeSelection = () => {
    if (!scanKey) return;
    place(active, { type: 'selection', faces: selectedFaces(scanKey), scanKey });
  };

  return (
    <ToolPanel
      toolId="align-faces"
      editingName={editTarget ? t('tools:alignAuto.alignment') : undefined}
      canCommit={result !== null}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <div className={styles.slots}>
          {ROLES.map((role) => (
            <SlotRow
              key={role}
              role={role}
              input={draft.slots[role]}
              name={inputName(draft.slots[role])}
              active={role === active}
              problem={problems[role]}
              fit={result?.inputs.find((fit) => fit.role === role)}
              onActivate={() => setActive(role)}
              onClear={() => place(role, null)}
            />
          ))}
        </div>
        <Button
          disabled={selectionCount === 0}
          data-testid="align-take-selection"
          onClick={takeSelection}
        >
          {t(`${KEY}.takeSelection`, { role: t(`${KEY}.roles.${active}`) })}
        </Button>
        <p className={styles.hint}>{t(`${KEY}.pickHint`)}</p>
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <AdjustControls
          adjust={draft.adjust}
          onAdjust={(action: AdjustAction) =>
            updateDraft((value) => ({ ...value, adjust: applyAdjust(value.adjust, action) }))
          }
        />
      </PanelSection>
      <AlignmentResult
        preview={preview}
        commitError={commit.error}
        idleText={t(`${KEY}.inputsFirst`)}
      />
    </ToolPanel>
  );
}
