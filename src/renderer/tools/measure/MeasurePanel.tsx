import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { MeasureItem } from '@shared/protocol/generated/inspection';

import { describeError } from '../../kernel/describeError';
import { documentStore, useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { useViewport } from '../../viewport/api';
import { ToolPanel } from '../framework/ToolPanel';
import { usePreview } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import { MeasureResultSection } from './MeasureResultSection';
import {
  type Slots,
  itemFromObject,
  itemFromPick,
  itemKey,
  itemLabel,
  measureOptions,
  withPicked,
} from './measureItems';
import styles from './MeasurePanel.module.css';

const TOOL_ID = 'measure';
const NONE = '';

/**
 * Distance, angle and diameters between two items picked in the viewport or the tree,
 * or chosen in the fields. Values only; nothing is added to the project.
 */
export function MeasurePanel({ close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'common']);
  const snapshot = useDocument((state) => state.snapshot);
  const viewport = useViewport();
  const [slots, setSlots] = useState<Slots>([null, null]);

  useEffect(() => {
    if (!viewport) return;
    return viewport.addInteraction({
      onPointerDown: (event) => {
        if (event.button !== 0 || event.ctrl || event.shift || event.alt) return false;
        const current = documentStore.getState().snapshot;
        if (!current) return false;
        const item = itemFromPick(
          viewport.pick(event.screen, { kinds: ['body', 'item'] }),
          current,
        );
        if (!item) return false;
        setSlots((previous) => withPicked(previous, item));
        return true;
      },
    });
  }, [viewport]);

  useEffect(
    () =>
      objectSelectionStore.subscribe((state, previous) => {
        const current = documentStore.getState().snapshot;
        if (!current || state.selected === previous.selected) return;
        const item = itemFromObject(state.selected[0], current);
        if (item) setSlots((slots) => withPicked(slots, item));
      }),
    [],
  );

  const [a, b] = slots;
  // A new revision (refit, undo) measures again with the same items.
  const revision = snapshot?.revision;
  const params = useMemo(() => (a && revision !== undefined ? { a, b } : null), [a, b, revision]);
  const result = usePreview('inspection.measure', params, TOOL_ID);

  if (!snapshot) return null;
  const options = measureOptions(snapshot, t);
  const choices = (item: MeasureItem | null) => {
    const listed = options.map((option) => ({ value: option.key, label: option.label }));
    const picked =
      item && !options.some((option) => option.key === itemKey(item))
        ? [{ value: itemKey(item), label: itemLabel(item, snapshot, t) }]
        : [];
    return [{ value: NONE, label: t('measure.none') }, ...picked, ...listed];
  };
  const choose = (index: 0 | 1, key: string) => {
    const option = options.find((candidate) => candidate.key === key);
    const item = key === NONE ? null : (option?.item ?? slots[index]);
    setSlots(index === 0 ? [item, slots[1]] : [slots[0], item]);
  };

  return (
    <ToolPanel toolId={TOOL_ID} canCommit onCommit={close} onCancel={close}>
      <PanelSection title={t('common:sections.input')}>
        {([0, 1] as const).map((index) => (
          <PropertyRow
            key={index}
            label={t(index === 0 ? 'measure.first' : 'measure.second')}
            htmlFor={`measure-item-${index}`}
          >
            <Select
              id={`measure-item-${index}`}
              testId={`measure-item-${index}`}
              value={slots[index] ? itemKey(slots[index]) : NONE}
              options={choices(slots[index])}
              onChange={(key) => choose(index, key)}
            />
          </PropertyRow>
        ))}
        <p className={styles.hint}>{t('measure.pickHint')}</p>
      </PanelSection>
      <MeasureResultSection
        computing={result.status === 'computing'}
        result={result.status === 'ok' ? result.result : null}
        second={b !== null}
      />
      {result.status === 'error' && (
        <InlineMessage severity="error" details={result.error.details}>
          {describeError(result.error, t)}
        </InlineMessage>
      )}
    </ToolPanel>
  );
}
