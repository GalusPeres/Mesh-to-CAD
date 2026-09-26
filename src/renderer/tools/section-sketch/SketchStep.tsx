import { Circle, CornerDownRight, Link2, Slash, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { SectionResult } from '@shared/protocol/generated/sketch';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { toFailure } from '../framework/hooks';
import { entityLabels } from './describe';
import { pointOf, xy } from './draftGeometry';
import {
  type EditResult,
  addCircle,
  closeGap,
  deleteEntity,
  formCorner,
  lineBetween,
} from './edits';
import { EntityEditor } from './EntityEditor';
import { EntityList } from './EntityList';
import {
  type SketchMode,
  enterSketchMode,
  leaveSketchMode,
  setSketchActions,
  updateSketchSession,
} from './sketchSession';
import { pickEntity, pickPoint, snapTargets, snapToTarget } from './sketchPicking';
import type { Vec2 } from './sketchMath';
import styles from './SketchPanel.module.css';
import { SketchResult } from './SketchResult';
import type { SketchDraft } from './useSketchDraft';
import { useSketchViewport } from './useSketchViewport';

const K = 'sectionSketch';

interface SketchStepProps {
  sketch: SketchDraft;
  section: SectionResult | null;
  caption: string;
  planeText: string;
  refitting: boolean;
  onChangePlane: () => void;
  onRefit: () => void;
}

interface Notice {
  severity: 'info' | 'warning';
  text: string;
}

/** Step 2, sketch mode: drawing tools, entities with numeric editing, result. */
export function SketchStep(props: SketchStepProps) {
  const { sketch, section, caption, planeText, refitting, onChangePlane, onRefit } = props;
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const { draft } = sketch;
  const state = sketch.fit ?? sketch.lastFit;
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<SketchMode>('select');
  const [pending, setPending] = useState<string | null>(null);
  const [circle, setCircle] = useState<{ center: Vec2; radius: number }>({
    center: [0, 0],
    radius: 5,
  });
  const [notice, setNotice] = useState<Notice | null>(null);
  const labels = useMemo(() => entityLabels(draft, t), [draft, t]);
  const selectedEntity = draft.entities.find((entity) => entity.id === selected) ?? null;
  const selectedFit = sketch.fit?.fits.find((fit) => fit.entity === selected) ?? null;

  const edit = sketch.edit;
  const apply = useCallback(
    (result: EditResult) => {
      if (result.ok) edit(result.sketch);
      setNotice(
        result.ok ? null : { severity: 'warning', text: t(`${K}.editFailed.${result.reason}`) },
      );
    },
    [edit, t],
  );
  const startMode = useCallback((next: SketchMode) => {
    setMode(next);
    setPending(null);
    setNotice(null);
  }, []);
  const remove = useCallback(
    (id: string | null) => {
      if (!id) return;
      edit(deleteEntity(draft, id));
      setSelected(null);
    },
    [edit, draft],
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

  const frame = state?.frame ?? section?.frame ?? null;
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
  const highlight = useMemo(() => {
    const points: Vec2[] =
      mode === 'line' && pending
        ? [xy(pointOf(draft, pending))]
        : mode === 'circle'
          ? [circle.center]
          : [];
    const gaps = state?.profile.gaps.map(([u, v]): Vec2 => [u, v]) ?? [];
    return { selected, pending: mode === 'corner' && pending ? [pending] : [], points, gaps };
  }, [selected, mode, pending, draft, circle.center, state]);

  const paint = (points: Vec2[]) => {
    kernel()
      .call('sketch.fitEntity', {
        sketch: draft,
        points: new Float64Array(points.flat()),
        kind: 'auto',
      })
      .result.then(async (fitted) => {
        const refitted = await kernel().call('sketch.autoFit', {
          sketch: fitted.sketch,
          refit: true,
        }).result;
        sketch.accept(refitted);
        setSelected(fitted.entity);
        setNotice({
          severity: 'info',
          text: t(`${K}.painted`, { value: format.length(fitted.maxDistance) }),
        });
      })
      .catch((error: unknown) => {
        setNotice({ severity: 'warning', text: describeError(toFailure(error), t) });
      });
  };

  const { project } = useSketchViewport({
    step: 'sketch',
    section: drawing,
    frame,
    sketch: draft,
    fits: sketch.fit?.fits ?? [],
    highlight,
    cut: null,
    handlers: {
      click: (cursor, atPlane, alt) => {
        if (!frame || !project) return;
        if (mode === 'select') {
          setSelected(pickEntity(draft, frame, project, cursor));
          return;
        }
        if (mode === 'circle') {
          if (!atPlane) return;
          const center = alt
            ? atPlane
            : snapToTarget(snapTargets(draft), frame, project, cursor, atPlane);
          setCircle((previous) => ({ ...previous, center }));
          return;
        }
        const hit =
          mode === 'corner'
            ? pickEntity(draft, frame, project, cursor)
            : pickPoint(draft, frame, project, cursor);
        if (!hit) return;
        if (!pending) {
          setPending(hit);
          return;
        }
        apply(
          mode === 'corner' ? formCorner(draft, pending, hit) : lineBetween(draft, pending, hit),
        );
        startMode('select');
      },
      paint,
      abort: () => {
        if (mode === 'select') return false;
        startMode('select');
        return true;
      },
    },
  });

  const modeHint =
    mode === 'corner'
      ? t(`${K}.mode.${pending ? 'cornerSecond' : 'cornerFirst'}`)
      : mode === 'line'
        ? t(`${K}.mode.${pending ? 'lineSecond' : 'lineFirst'}`)
        : mode === 'circle'
          ? t(`${K}.mode.circle`)
          : null;
  const toggle = (next: SketchMode) => () => startMode(mode === next ? 'select' : next);
  const setCircleCenter = (index: 0 | 1, value: number) =>
    setCircle((previous) => ({
      ...previous,
      center: index === 0 ? [value, previous.center[1]] : [previous.center[0], value],
    }));
  const addTypedCircle = () => {
    edit(addCircle(draft, circle.center, circle.radius));
    startMode('select');
  };

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
        <div className={styles.toolbar} role="toolbar" aria-label={t(`${K}.draw`)}>
          <IconButton
            icon={CornerDownRight}
            label={t(`${K}.actions.corner`)}
            shortcut="K"
            pressed={mode === 'corner'}
            onClick={toggle('corner')}
          />
          <IconButton
            icon={Slash}
            label={t(`${K}.actions.line`)}
            shortcut="L"
            pressed={mode === 'line'}
            onClick={toggle('line')}
          />
          <IconButton
            icon={Circle}
            label={t(`${K}.actions.circle`)}
            shortcut="C"
            pressed={mode === 'circle'}
            onClick={toggle('circle')}
          />
          <IconButton
            icon={Link2}
            label={t(`${K}.actions.closeGap`)}
            disabled={!state || state.profile.gaps.length === 0}
            onClick={() => apply(closeGap(draft))}
          />
        </div>
        {modeHint && <InlineMessage severity="info">{modeHint}</InlineMessage>}
        {mode === 'circle' && (
          <>
            {([0, 1] as const).map((index) => (
              <PropertyRow
                key={index}
                label={t(`${K}.field.${index ? 'centerY' : 'centerX'}`)}
                htmlFor={`sketch-circle-${index}`}
              >
                <NumberField
                  id={`sketch-circle-${index}`}
                  value={circle.center[index]}
                  onCommit={(value) => setCircleCenter(index, value)}
                />
              </PropertyRow>
            ))}
            <PropertyRow label={t(`${K}.field.radius`)} htmlFor="sketch-circle-radius">
              <NumberField
                id="sketch-circle-radius"
                value={circle.radius}
                min={0.01}
                onCommit={(radius) => setCircle((previous) => ({ ...previous, radius }))}
              />
            </PropertyRow>
            <Button onClick={addTypedCircle}>{t(`${K}.actions.addCircle`)}</Button>
          </>
        )}
        {notice && <InlineMessage severity={notice.severity}>{notice.text}</InlineMessage>}

        <h3 className={styles.subheading}>{t(`${K}.entities`)}</h3>
        <EntityList
          sketch={draft}
          labels={labels}
          fits={sketch.fit?.fits ?? []}
          selected={selected}
          onSelect={setSelected}
        />
        {selectedEntity && (
          <>
            <h3 className={styles.subheading}>{labels.get(selectedEntity.id)}</h3>
            {selectedFit?.maxDistance != null && (
              <p className={styles.hint}>
                {t(`${K}.deviation`, { value: format.length(selectedFit.maxDistance) })}
              </p>
            )}
            <EntityEditor sketch={draft} entity={selectedEntity} onEdit={edit} />
            <Button variant="ghost" onClick={() => remove(selectedEntity.id)}>
              <Trash2 size={16} aria-hidden /> {t(`${K}.actions.delete`)}
            </Button>
          </>
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
        onEdit={edit}
      />
    </>
  );
}
