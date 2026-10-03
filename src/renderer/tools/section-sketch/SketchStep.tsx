import { Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import type { EntityFitInfo, SectionResult } from '@shared/protocol/generated/sketch';

import { useFormatter } from '../../i18n/useFormatter';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { entityLabels } from './describe';
import { deviationLabels } from './deviationLabels';
import { pointOf, xy } from './draftGeometry';
import { addCircle, closeGap, deleteEntities } from './edits';
import { EntityEditor } from './EntityEditor';
import { EntityList } from './EntityList';
import { groupOf, selectedEntities, sketchGroups } from './sketchGroups';
import {
  enterSketchMode,
  leaveSketchMode,
  setSketchActions,
  updateSketchSession,
} from './sketchSession';
import type { Vec2 } from './sketchMath';
import styles from './SketchPanel.module.css';
import { SketchResult } from './SketchResult';
import { SketchToolbar } from './SketchToolbar';
import { shapeLabel, shapeSizes } from './shapeSizes';
import type { SketchDraft } from './useSketchDraft';
import { useSketchGestures } from './useSketchGestures';
import { useSketchViewport } from './useSketchViewport';

const K = 'sectionSketch';
const NO_FITS: readonly EntityFitInfo[] = [];

interface SketchStepProps {
  sketch: SketchDraft;
  section: SectionResult | null;
  caption: string;
  planeText: string;
  refitting: boolean;
  onChangePlane: () => void;
  onRefit: () => void;
}

/** Step 2, sketch mode: gestures in the view, entities with numeric editing, result. */
export function SketchStep(props: SketchStepProps) {
  const { sketch, section, caption, planeText, refitting, onChangePlane, onRefit } = props;
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const { draft, edit } = sketch;
  const state = sketch.fit ?? sketch.lastFit;
  const frame = state?.frame ?? section?.frame ?? null;
  const gestures = useSketchGestures(sketch, section, frame);
  const { mode, startMode, pending, selected, setSelected, circle, apply } = gestures;
  const labels = useMemo(() => entityLabels(draft, t), [draft, t]);
  const groups = useMemo(() => sketchGroups(draft), [draft]);
  const selectedIds = useMemo(() => selectedEntities(groups, selected), [groups, selected]);
  const selectedShape = draft.shapes.find((shape) => shape.id === selected) ?? null;
  const selectedEntity = draft.entities.find((entity) => entity.id === selected) ?? null;
  const selectedFit = sketch.fit?.fits.find((fit) => fit.entity === selected) ?? null;
  const fits = sketch.fit?.fits ?? state?.fits ?? NO_FITS;

  const remove = useCallback(
    (id: string | null) => {
      if (!id) return;
      edit(deleteEntities(draft, selectedEntities(groups, id)));
      setSelected(null);
    },
    [edit, draft, groups, setSelected],
  );

  useEffect(() => {
    enterSketchMode();
    return leaveSketchMode;
  }, []);
  useEffect(() => {
    setSketchActions({
      setMode: startMode,
      closeGap: () => apply(closeGap(draft)),
      deleteSelected: () => remove(selected),
    });
  }, [startMode, apply, draft, remove, selected]);
  useEffect(() => {
    updateSketchSession({ mode, caption, profile: state?.profile ?? null });
  }, [mode, caption, state]);

  const drawing = useMemo(
    () =>
      section
        ? {
            frame: section.frame,
            polylines: section.polylines,
            closed: section.closed,
            folded: section.folded,
          }
        : null,
    [section],
  );
  const selectedGroup = groupOf(groups, selected)?.id ?? null;
  const deviation = useMemo(
    () =>
      deviationLabels(
        draft,
        fits,
        [gestures.hoveredGroup, selectedGroup].filter((id) => id !== null),
      ),
    [draft, fits, gestures.hoveredGroup, selectedGroup],
  );
  const highlight = useMemo(() => {
    const points: Vec2[] =
      mode === 'line' && pending
        ? [xy(pointOf(draft, pending))]
        : mode === 'circle'
          ? [circle.center]
          : [];
    return {
      selected: selectedIds,
      pending: mode === 'corner' && pending ? [pending] : [],
      points,
      gaps: state?.profile.gaps.map(([u, v]): Vec2 => [u, v]) ?? [],
      outline: gestures.outline,
      joint: gestures.joint,
      labels: deviation,
    };
  }, [
    selectedIds,
    mode,
    pending,
    draft,
    circle.center,
    state,
    gestures.outline,
    gestures.joint,
    deviation,
  ]);

  useSketchViewport({
    step: 'sketch',
    section: drawing,
    frame,
    sketch: draft,
    fits,
    highlight,
    cut: null,
    handlers: gestures.handlers,
  });

  return (
    <>
      <PanelSection title={t('common:sections.input')}>
        <PropertyValue label={t(`${K}.sketchPlane`)} value={planeText} />
        {draft.section.type === 'planar' && (
          <PropertyValue
            label={t(`${K}.cut`)}
            value={t(`${K}.cutValue`, { value: format.length(draft.section.sectionOffset) })}
          />
        )}
        <Button variant="ghost" onClick={onChangePlane}>
          {t(`${K}.actions.changePlane`)}
        </Button>
      </PanelSection>

      <PanelSection title={t('common:sections.parameters')}>
        <SketchToolbar
          mode={mode}
          onMode={startMode}
          canCloseGap={!!state && state.profile.gaps.length > 0}
          onCloseGap={() => apply(closeGap(draft))}
          circle={circle}
          onCircle={gestures.setCircle}
          onAddCircle={() => {
            edit(addCircle(draft, circle.center, circle.radius));
            startMode('select');
          }}
        />
        {gestures.notice && (
          <InlineMessage severity={gestures.notice.severity}>{gestures.notice.text}</InlineMessage>
        )}

        <h3 className={styles.subheading}>{t(`${K}.entities`)}</h3>
        <EntityList
          sketch={draft}
          labels={labels}
          fits={fits}
          selected={selected}
          onSelect={setSelected}
        />
        {selectedShape && (
          <>
            <h3 className={styles.subheading}>{shapeLabel(selectedShape, t)}</h3>
            {Object.entries(shapeSizes(draft, selectedShape)).map(([name, value]) => (
              <PropertyValue
                key={name}
                label={t(`${K}.size.${name}`)}
                value={format.length(value)}
              />
            ))}
          </>
        )}
        {selectedEntity && (
          <>
            <h3 className={styles.subheading}>{labels.get(selectedEntity.id)}</h3>
            {selectedFit?.maxDistance != null && (
              <PropertyValue
                label={t(`${K}.result.deviation`)}
                value={format.length(selectedFit.maxDistance)}
              />
            )}
            <EntityEditor sketch={draft} entity={selectedEntity} onEdit={edit} />
          </>
        )}
        {selectedIds.length > 0 && (
          <Button variant="ghost" onClick={() => remove(selected)}>
            <Trash2 size={16} aria-hidden /> {t(`${K}.actions.delete`)}
          </Button>
        )}
      </PanelSection>

      <PanelSection title={t('common:sections.options')}>
        <Button onClick={onRefit} disabled={refitting}>
          {t(`${K}.actions.refit`)}
        </Button>
      </PanelSection>

      <SketchResult
        sketch={draft}
        labels={labels}
        state={state}
        current={!!sketch.fit}
        error={sketch.refitError}
        focus={highlight.selected.length ? highlight.selected : null}
        onEdit={edit}
      />
    </>
  );
}
