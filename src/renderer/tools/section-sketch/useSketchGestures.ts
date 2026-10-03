// The pointer in sketch mode: hover feedback, the status bar hint and what clicks
// and strokes do (sketchGestures.ts decides, this hook carries it out). Kernel
// gestures run one after another on the latest draft, so quick clicks on several
// buttons all land.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { SectionResult, SketchFrame } from '@shared/protocol/generated/sketch';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { useViewport } from '../../viewport/api';
import { toFailure } from '../framework/hooks';
import { type EditResult, formCorner, lineBetween } from './edits';
import { type Gesture, type GestureContext, gestureAt, strokeGesture } from './sketchGestures';
import { groupOf, sketchGroups } from './sketchGroups';
import { pickEntity, pickPoint, snapTargets, snapToTarget } from './sketchPicking';
import { type SketchMode, updateSketchSession } from './sketchSession';
import type { Vec2 } from './sketchMath';
import { shapeLabel, shapeSizeText } from './shapeSizes';
import type { SketchDraft } from './useSketchDraft';
import { useSketchToolInfo } from './useSketchToolInfo';
import type { SketchPointer, SketchPointerHandlers } from './useSketchViewport';

const K = 'sectionSketch';
const GESTURE_LANE = ':section-sketch';

export interface Notice {
  severity: 'info' | 'warning';
  text: string;
}

export interface Hover {
  gesture: Gesture;
  ctrl: boolean;
}

const IDLE: Hover = { gesture: { kind: 'none' }, ctrl: false };

function polyline(array: Float32Array): Vec2[] {
  const points: Vec2[] = [];
  for (let i = 0; i + 1 < array.length; i += 2) points.push([array[i] ?? 0, array[i + 1] ?? 0]);
  return points;
}

function sameHover(a: Hover, b: Hover): boolean {
  return a.ctrl === b.ctrl && JSON.stringify(a.gesture) === JSON.stringify(b.gesture);
}

export function useSketchGestures(
  sketch: SketchDraft,
  section: SectionResult | null,
  frame: SketchFrame | null,
) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const viewport = useViewport();
  const { draft, edit, accept } = sketch;
  const [mode, setMode] = useState<SketchMode>('select');
  const [pending, setPending] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [circle, setCircle] = useState<{ center: Vec2; radius: number }>({
    center: [0, 0],
    radius: 5,
  });
  const [notice, setNotice] = useState<Notice | null>(null);
  const [hover, setHover] = useState<Hover>(IDLE);
  const [running, setRunning] = useState(0);
  const latest = useRef(draft);
  const queue = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    latest.current = draft;
  }, [draft]);

  const loops = useMemo(
    () => (section ? section.polylines.filter((_, i) => section.closed[i]).map(polyline) : []),
    [section],
  );
  useSketchToolInfo({ sketch: draft, frame, loops, busy: running > 0 });
  const context = useCallback(
    (): GestureContext | null =>
      frame && viewport
        ? { sketch: latest.current, loops, frame, project: (p) => viewport.worldToScreen(p) }
        : null,
    [frame, viewport, loops],
  );

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

  /** Runs kernel gestures one at a time, each on the draft its predecessor left. */
  const enqueue = useCallback(
    (task: () => Promise<void>) => {
      setRunning((count) => count + 1);
      queue.current = queue.current
        .then(task)
        .catch((error: unknown) => {
          if (!isSilentFailure(error)) {
            setNotice({ severity: 'warning', text: describeError(toFailure(error), t) });
          }
        })
        .finally(() => setRunning((count) => count - 1));
    },
    [t],
  );

  const fitOutline = (at: Vec2) =>
    enqueue(async () => {
      const result = await kernel().call(
        'sketch.fitOutline',
        { sketch: latest.current, point: [at[0], at[1]] },
        { lane: `sketch.fitOutline${GESTURE_LANE}` },
      ).result;
      latest.current = result.fit.sketch;
      accept(result.fit);
      const fits = result.fit.fits.filter((fit) => result.entities.includes(fit.entity));
      const deviation = Math.max(0, ...fits.map((fit) => fit.maxDistance ?? 0));
      const shape = result.fit.sketch.shapes.find((s) =>
        s.entities.includes(result.entities[0] ?? ''),
      );
      setNotice({
        severity: fits.every((fit) => fit.passed !== false) ? 'info' : 'warning',
        text: shape
          ? t(`${K}.fitted`, {
              shape: shapeLabel(shape, t),
              size: shapeSizeText(result.fit.sketch, shape, format),
              value: format.length(deviation),
            })
          : t(`${K}.fittedFree`, {
              count: result.entities.length,
              value: format.length(deviation),
            }),
      });
    });

  const fillet = (point: string) =>
    enqueue(async () => {
      const result = await kernel().call(
        'sketch.fillet',
        { sketch: latest.current, point },
        { lane: `sketch.fillet${GESTURE_LANE}` },
      ).result;
      latest.current = result.fit.sketch;
      accept(result.fit);
      setNotice({
        severity: 'info',
        text: t(`${K}.filleted`, {
          value: format.length(result.radius),
          measured: format.length(result.measured),
        }),
      });
    });

  const paint = (points: Vec2[]) =>
    enqueue(async () => {
      const fitted = await kernel().call('sketch.fitEntity', {
        sketch: latest.current,
        points: new Float64Array(points.flat()),
        kind: 'auto',
      }).result;
      const refitted = await kernel().call('sketch.autoFit', { sketch: fitted.sketch, refit: true })
        .result;
      latest.current = refitted.sketch;
      accept(refitted);
      setNotice({
        severity: 'info',
        text: t(`${K}.painted`, { value: format.length(fitted.maxDistance) }),
      });
    });

  const act = (gesture: Gesture) => {
    if (gesture.kind === 'select') {
      // A click selects the whole shape or profile first, a second click the entity.
      const group = groupOf(sketchGroups(latest.current), gesture.entity)?.id ?? null;
      setSelected(
        group && selected !== group && selected !== gesture.entity ? group : gesture.entity,
      );
    } else if (gesture.kind === 'outline') fitOutline(gesture.at);
    else if (gesture.kind === 'fillet') fillet(gesture.point);
    else if (gesture.kind === 'corner')
      apply(formCorner(latest.current, gesture.first, gesture.second));
    else setSelected(null);
  };

  const click = ({ cursor, atPlane, ctrl, alt }: SketchPointer) => {
    const current = context();
    if (!current) return;
    if (mode === 'select') return act(gestureAt(current, cursor, atPlane, ctrl));
    if (mode === 'circle') {
      if (!atPlane) return;
      const center = alt
        ? atPlane
        : snapToTarget(snapTargets(draft), current.frame, current.project, cursor, atPlane);
      setCircle((previous) => ({ ...previous, center }));
      return;
    }
    const hit =
      mode === 'corner'
        ? pickEntity(draft, current.frame, current.project, cursor)
        : pickPoint(draft, current.frame, current.project, cursor);
    if (!hit) return;
    if (!pending) return setPending(hit);
    apply(mode === 'corner' ? formCorner(draft, pending, hit) : lineBetween(draft, pending, hit));
    startMode('select');
  };

  const handlers: SketchPointerHandlers = {
    click,
    paint,
    stroke: (path) => {
      const current = context();
      if (current && mode === 'select') act(strokeGesture(current, path));
    },
    hover: ({ cursor, atPlane, ctrl }) => {
      const current = context();
      if (!current || mode !== 'select') return;
      const next = { gesture: gestureAt(current, cursor, atPlane, ctrl), ctrl };
      setHover((previous) => (sameHover(previous, next) ? previous : next));
    },
    abort: () => {
      if (mode === 'select') return false;
      startMode('select');
      return true;
    },
  };

  const hint =
    running > 0
      ? 'working'
      : mode === 'corner'
        ? pending
          ? 'cornerSecond'
          : 'cornerFirst'
        : mode === 'line'
          ? pending
            ? 'lineSecond'
            : 'lineFirst'
          : mode === 'circle'
            ? 'circle'
            : hover.gesture.kind === 'none'
              ? hover.ctrl
                ? 'idleCtrl'
                : 'idle'
              : hover.gesture.kind;
  useEffect(() => {
    updateSketchSession({ hint });
  }, [hint]);

  const gesture = hover.gesture;
  const outline = gesture.kind === 'outline' ? (loops[gesture.loop] ?? null) : null;
  const joint =
    gesture.kind === 'fillet' ? (draft.points.find((p) => p.id === gesture.point) ?? null) : null;
  const hovered =
    gesture.kind === 'select' ? (groupOf(sketchGroups(draft), gesture.entity)?.id ?? null) : null;
  return {
    mode,
    startMode,
    pending,
    selected,
    setSelected,
    circle,
    setCircle,
    notice,
    apply,
    handlers,
    outline,
    joint: joint ? ([joint.x, joint.y] as Vec2) : null,
    hoveredGroup: hovered,
  };
}
