import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { CombineParams, CombineParamsInput } from '@shared/protocol/generated/feature-combine';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import { availableBodies, storedParams, toolsProblem } from '../extrude/solid/model';
import {
  BodySelect,
  InputProblemMessage,
  SolidResult,
  useBodyLabel,
} from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';

type Operation = CombineParams['operation'];
const OPERATIONS: readonly Operation[] = ['add', 'cut', 'intersect'];

/** Unite, subtract or intersect bodies; the tool bodies disappear unless kept. */
export function CombinePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const bodyLabel = useBodyLabel();
  const stored = useMemo(
    () => storedParams<CombineParams>(snapshot, editTarget, 'combine'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const bodies = useMemo(
    () => (snapshot ? availableBodies(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );

  const [targetBody, setTargetBody] = useState<string | null>(() => {
    if (stored) return stored.targetBody;
    const selected = objectSelectionStore
      .getState()
      .selected.filter((item) => item.kind === 'body');
    return selected[0]?.id ?? bodies[0]?.id ?? null;
  });
  const [tools, setTools] = useState<string[]>(() => {
    if (stored) return stored.tools;
    const selected = objectSelectionStore
      .getState()
      .selected.filter((item) => item.kind === 'body');
    return selected.slice(1).map((item) => item.id);
  });
  const [operation, setOperation] = useState<Operation>(stored?.operation ?? 'add');
  const [keepTools, setKeepTools] = useState(stored?.keepTools ?? false);

  const problem = toolsProblem(targetBody, tools);
  const params = useMemo<CombineParamsInput | null>(
    () => (targetBody && !problem ? { targetBody, tools, operation, keepTools } : null),
    [targetBody, problem, tools, operation, keepTools],
  );
  const { preview, commit, deviation, previewOk } = useSolidFeature(
    'combine',
    'combine',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  const toggleTool = (id: string, checked: boolean) =>
    setTools((current) =>
      checked
        ? [...current.filter((tool) => tool !== id), id]
        : current.filter((tool) => tool !== id),
    );

  return (
    <ToolPanel
      toolId="combine"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {bodies.length < 2 ? (
          <InlineMessage severity="info">{t('tools:combine.twoBodies')}</InlineMessage>
        ) : (
          <>
            <BodySelect
              label={t('tools:extrude.solid.targetBody')}
              value={targetBody}
              bodies={bodies}
              bodyLabel={bodyLabel}
              testId="combine-target"
              onChange={(id) => {
                setTargetBody(id);
                setTools((current) => current.filter((tool) => tool !== id));
              }}
            />
            <p>{t('tools:combine.tools')}</p>
            {bodies
              .filter((body) => body.id !== targetBody)
              .map((body) => (
                <Checkbox
                  key={body.id}
                  checked={tools.includes(body.id)}
                  label={bodyLabel(body)}
                  testId={`combine-tool-${body.id}`}
                  onChange={(checked) => toggleTool(body.id, checked)}
                />
              ))}
          </>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:extrude.solid.operation')}>
          <SegmentedControl<Operation>
            value={operation}
            ariaLabel={t('tools:extrude.solid.operation')}
            segments={OPERATIONS.map((value) => ({
              value,
              label: t(`tools:extrude.solid.operations.${value}`),
            }))}
            onChange={setOperation}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <Checkbox
          checked={keepTools}
          label={t('tools:combine.keepTools')}
          onChange={setKeepTools}
        />
        <InputProblemMessage problem={bodies.length < 2 ? null : problem} />
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} deviation={deviation} />
    </ToolPanel>
  );
}
