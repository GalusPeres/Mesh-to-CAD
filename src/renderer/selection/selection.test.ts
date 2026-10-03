import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { setDocumentSnapshot } from '../state/documentStore';
import { clearHistory, entryToUndo, historyStore } from '../state/historyStore';
import {
  type ScreenPoint,
  type Viewport,
  type ViewportPointerEvent,
  registerViewport,
} from '../viewport/api';
import { redo, undo } from '../app/edit.commands';
import { innerRing, outerRing } from './faceMask';
import { facesWithLabels } from './regionActions';
import { createBrushMode } from './modes/brushMode';
import { createShapeMode } from './modes/shapeMode';
import { steppedTolerance } from './modes/smartMode';
import { optionsFromSettings, selectionOptionsStore } from './selectionOptions';
import { installSelectionHistory, selectionMask, setSelected } from './selectionActions';
import { growSelection, hideSelection, invertSelection, shrinkSelection } from './selectionEdits';
import { resetSelectionMemory, selectionStore, switchScan } from './selectionStore';
import {
  LassoPath,
  pointInPolygon,
  polygonArea,
  rectanglePolygon,
  strokeSamples,
} from './screenShapes';

/** A strip of faces 0..n-1 where face i neighbours i-1 and i+1. */
function stripNeighbours(count: number): Int32Array {
  const neighbours = new Int32Array(count * 3).fill(-1);
  for (let face = 0; face < count; face += 1) {
    neighbours[face * 3] = face > 0 ? face - 1 : -1;
    neighbours[face * 3 + 1] = face < count - 1 ? face + 1 : -1;
  }
  return neighbours;
}

function snapshot(key: string, faceCount: number): DocumentSnapshot {
  return {
    revision: 1,
    document: { scan: { key, faceCount }, regions: { labels: null, items: [] } },
    scene: { regions: null },
  } as unknown as DocumentSnapshot;
}

interface StubViewport extends Viewport {
  selected: Uint8Array;
  pickedCircles: { at: ScreenPoint; radius: number; visibleOnly: boolean }[];
}

/**
 * A viewport over a strip of `faceCount` faces laid out along x: face i covers
 * x in [10 i, 10 i + 10). Circle picking returns the faces the circle overlaps.
 */
function stubViewport(scanKey: string, faceCount: number): StubViewport {
  const selected = new Uint8Array(faceCount);
  const pickedCircles: StubViewport['pickedCircles'] = [];
  const inRange = (from: number, to: number) => {
    const faces: number[] = [];
    for (let face = 0; face < faceCount; face += 1) {
      if (face * 10 + 10 > from && face * 10 < to) faces.push(face);
    }
    return Uint32Array.from(faces);
  };
  const viewport = {
    selected,
    pickedCircles,
    scan: {
      faceCount,
      scanKey,
      setSelection: (mask: Uint8Array) => selected.set(mask),
      updateSelection: (faces: Uint32Array, value: boolean) => {
        for (const face of faces) selected[face] = value ? 1 : 0;
      },
      setHover: vi.fn(),
      setHidden: vi.fn(),
      setFaceStates: vi.fn(),
      setRegions: vi.fn(),
      setDeviation: vi.fn(),
      setOpacity: vi.fn(),
    },
    pickScanFacesInCircle: (at: ScreenPoint, radius: number, options: { visibleOnly: boolean }) => {
      pickedCircles.push({ at, radius, visibleOnly: options.visibleOnly });
      return inRange(at.x - radius, at.x + radius);
    },
    pickScanFacesInPolygon: (polygon: Float32Array) => {
      const xs = polygon.filter((_value, index) => index % 2 === 0);
      return Promise.resolve(inRange(Math.min(...xs), Math.max(...xs)));
    },
    scanTopology: () =>
      Promise.resolve({
        neighbours: stripNeighbours(faceCount),
        centroids: new Float32Array(faceCount * 3),
      }),
    invalidate: vi.fn(),
  };
  return viewport as unknown as StubViewport;
}

function pointer(x: number, extra: Partial<ViewportPointerEvent> = {}): ViewportPointerEvent {
  return {
    screen: { x, y: 0 },
    button: 0,
    buttons: 1,
    ctrl: false,
    shift: false,
    alt: false,
    ...extra,
  };
}

function selectedList(): number[] {
  const mask = selectionMask();
  return mask ? [...mask.keys()].filter((face) => mask[face]) : [];
}

describe('face masks', () => {
  it('grows and shrinks the selection by one ring', () => {
    const neighbours = stripNeighbours(10);
    const mask = new Uint8Array(10);
    mask.set([1, 1, 1], 4);
    expect([...outerRing(mask, neighbours, null)]).toEqual([3, 7]);
    const hidden = new Uint8Array(10);
    hidden[3] = 1;
    expect([...outerRing(mask, neighbours, hidden)]).toEqual([7]);
    expect([...innerRing(mask, neighbours)]).toEqual([4, 6]);
  });
});

describe('regions', () => {
  it('collects the faces of several region labels', () => {
    const labels = Uint16Array.from([0, 2, 1, 2, 3, 1]);
    expect([...facesWithLabels(labels, new Set([1, 2]))]).toEqual([1, 2, 3, 5]);
    expect(facesWithLabels(labels, new Set([9]))).toHaveLength(0);
  });
});

describe('screen shapes', () => {
  it('tests points against a lasso polygon', () => {
    const square = Float32Array.from([0, 0, 10, 0, 10, 10, 0, 10]);
    expect(pointInPolygon({ x: 5, y: 5 }, square)).toBe(true);
    expect(pointInPolygon({ x: 15, y: 5 }, square)).toBe(false);
    // A concave "C": the notch is outside.
    const c = Float32Array.from([0, 0, 10, 0, 10, 3, 3, 3, 3, 7, 10, 7, 10, 10, 0, 10]);
    expect(pointInPolygon({ x: 6, y: 5 }, c)).toBe(false);
    expect(pointInPolygon({ x: 1, y: 5 }, c)).toBe(true);
  });

  it('builds rectangles from any two corners', () => {
    const rectangle = rectanglePolygon({ x: 10, y: 8 }, { x: 2, y: 4 });
    expect([...rectangle]).toEqual([2, 4, 10, 4, 10, 8, 2, 8]);
    expect(polygonArea(rectangle)).toBe(32);
  });

  it('samples fast strokes without gaps and thins lasso points', () => {
    const samples = strokeSamples({ x: 0, y: 0 }, { x: 30, y: 0 }, 10);
    expect(samples.map((point) => point.x)).toEqual([10, 20, 30]);
    const lasso = new LassoPath(3);
    expect(lasso.add({ x: 0, y: 0 })).toBe(true);
    expect(lasso.add({ x: 5, y: 0 })).toBe(true);
    expect(lasso.add({ x: 6, y: 1 })).toBe(false);
    expect(lasso.pointCount).toBe(2);
  });
});

describe('selection', () => {
  let uninstall: () => void;

  beforeEach(() => {
    clearHistory();
    switchScan(null);
    resetSelectionMemory();
    selectionOptionsStore.setState(optionsFromSettings(undefined));
    vi.stubGlobal('requestAnimationFrame', () => 1);
    vi.stubGlobal('cancelAnimationFrame', () => undefined);
    uninstall = installSelectionHistory();
  });

  afterEach(() => {
    uninstall();
    registerViewport(null);
    setDocumentSnapshot(null);
    vi.unstubAllGlobals();
  });

  it('paints a brush stroke as one undo step and shows it in the viewport', async () => {
    const viewport = stubViewport('scan:a', 20);
    registerViewport(viewport);
    setDocumentSnapshot(snapshot('scan:a', 20));
    selectionOptionsStore.setState({ brushRadius: 4 });
    const brush = createBrushMode(viewport);

    brush.interaction.onPointerDown?.(pointer(15));
    brush.interaction.onPointerMove?.(pointer(45));
    brush.interaction.onPointerUp?.(pointer(45));

    expect(selectedList()).toEqual([1, 2, 3, 4]);
    expect([...viewport.selected.keys()].filter((face) => viewport.selected[face])).toEqual([
      1, 2, 3, 4,
    ]);
    expect(viewport.pickedCircles.every((pick) => pick.visibleOnly)).toBe(true);
    expect(historyStore.getState().entries).toHaveLength(1);

    await undo();
    expect(selectedList()).toEqual([]);
    expect(viewport.selected.every((value) => value === 0)).toBe(true);
    await redo();
    expect(selectedList()).toEqual([1, 2, 3, 4]);

    // Ctrl removes; the second stroke is its own undo step.
    brush.interaction.onPointerDown?.(pointer(30, { ctrl: true }));
    brush.interaction.onPointerUp?.(pointer(30, { ctrl: true }));
    expect(selectedList()).toEqual([1, 4]);
    await undo();
    expect(selectedList()).toEqual([1, 2, 3, 4]);
    brush.dispose();
  });

  it('resizes the brush with the bracket keys and Ctrl + wheel', () => {
    const brush = createBrushMode(stubViewport('scan:a', 4));
    const before = selectionOptionsStore.getState().brushRadius;
    brush.interaction.onKeyDown?.(new KeyboardEventStub(']') as unknown as KeyboardEvent);
    expect(selectionOptionsStore.getState().brushRadius).toBeGreaterThan(before);
    const handled = brush.interaction.onWheel?.({ ...pointer(0), ctrl: true, deltaY: 100 });
    expect(handled).toBe(true);
    expect(selectionOptionsStore.getState().brushRadius).toBe(before);
    expect(brush.interaction.onWheel?.({ ...pointer(0), deltaY: 100 })).toBe(false);
  });

  it('skips undo entries of another scan', async () => {
    const viewport = stubViewport('scan:a', 10);
    registerViewport(viewport);
    setDocumentSnapshot(snapshot('scan:a', 10));
    setSelected(Uint32Array.from([1, 2]), 1);

    setDocumentSnapshot(snapshot('scan:b', 10));
    expect(selectedList()).toEqual([]);
    await undo();
    expect(selectedList()).toEqual([]);
    expect(entryToUndo()).toBeUndefined();

    // Back on the first scan its selection is remembered.
    setDocumentSnapshot(snapshot('scan:a', 10));
    expect(selectedList()).toEqual([1, 2]);
    expect(selectionStore.getState().count).toBe(2);
  });

  it('grows, shrinks, inverts and hides with single undo steps', async () => {
    const viewport = stubViewport('scan:a', 10);
    registerViewport(viewport);
    setDocumentSnapshot(snapshot('scan:a', 10));
    setSelected(Uint32Array.from([4, 5]), 1);

    await growSelection();
    expect(selectedList()).toEqual([3, 4, 5, 6]);
    await shrinkSelection();
    expect(selectedList()).toEqual([4, 5]);
    await undo();
    expect(selectedList()).toEqual([3, 4, 5, 6]);

    hideSelection();
    expect(selectedList()).toEqual([]);
    expect(selectionStore.getState().hiddenCount).toBe(4);
    invertSelection();
    expect(selectedList()).toEqual([0, 1, 2, 7, 8, 9]);
    await undo();
    await undo();
    expect(selectedList()).toEqual([3, 4, 5, 6]);
    expect(selectionStore.getState().hiddenCount).toBe(0);
  });

  it('selects the faces inside a lasso and a rectangle', async () => {
    const viewport = stubViewport('scan:a', 10);
    registerViewport(viewport);
    setDocumentSnapshot(snapshot('scan:a', 10));
    const rectangle = createShapeMode(viewport, 'rectangle');
    rectangle.interaction.onPointerDown?.(pointer(21));
    rectangle.interaction.onPointerMove?.({ ...pointer(39), screen: { x: 39, y: 10 } });
    rectangle.interaction.onPointerUp?.(pointer(39));
    await vi.waitFor(() => expect(selectedList()).toEqual([2, 3]));

    const lasso = createShapeMode(viewport, 'lasso');
    lasso.interaction.onPointerDown?.(pointer(31, { ctrl: true }));
    lasso.interaction.onPointerMove?.({ ...pointer(35), screen: { x: 35, y: 10 } });
    lasso.interaction.onPointerMove?.({ ...pointer(38), screen: { x: 31, y: 12 } });
    lasso.interaction.onPointerUp?.(pointer(31));
    await vi.waitFor(() => expect(selectedList()).toEqual([2]));
    expect(historyStore.getState().entries).toHaveLength(2);
  });
});

describe('selection options', () => {
  it('fall back to defaults for invalid stored values', () => {
    expect(optionsFromSettings({ brushRadius: 9999, visibleOnly: 'yes' })).toMatchObject({
      brushRadius: 200,
      visibleOnly: true,
      throughPart: false,
      smartTolerance: null,
    });
  });

  it('step the smart-select tolerance within its range', () => {
    expect(steppedTolerance(0.1, true)).toBe(0.125);
    expect(steppedTolerance(0.125, false)).toBe(0.1);
    expect(steppedTolerance(10, true)).toBe(10);
  });
});

class KeyboardEventStub {
  constructor(readonly key: string) {}
  readonly ctrlKey = false;
  readonly altKey = false;
}
