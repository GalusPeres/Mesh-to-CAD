import { useEffect, useState } from 'react';
import { BufferGeometry, Float32BufferAttribute, LineBasicMaterial, LineSegments } from 'three';

import { useDocument } from '../../state/documentStore';
import { getViewport } from '../../viewport/api';
import { SCENE_COLORS } from '../../viewport/palette';
import { type Vec3, footprint, frameMapping } from './frameMath';

const AXIS_SHARE = 0.35;
const MIN_AXIS_MM = 5;

/** Face centroids of the displayed scan, loaded once per scan. */
function useDisplayedCentroids(): Float32Array | null {
  const scanKey = useDocument((state) => state.snapshot?.scene.scan?.key ?? null);
  const [centroids, setCentroids] = useState<{ key: string; points: Float32Array } | null>(null);
  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || !scanKey) return;
    let current = true;
    void viewport.scanTopology().then((topology) => {
      if (current) setCentroids({ key: scanKey, points: topology.centroids });
    });
    return () => {
      current = false;
    };
  }, [scanKey]);
  return centroids?.key === scanKey ? (centroids?.points ?? null) : null;
}

function segment(from: Vec3, to: Vec3): number[] {
  return [...from, ...to];
}

/**
 * Draws the previewed part frame over the scan as it is displayed now: the three
 * axes from the new origin in the axis colours and the outline of the part's
 * footprint on the new XY plane. The scan itself moves only when the alignment is
 * committed.
 */
export function useFrameOverlay(matrix: readonly number[] | null): void {
  const transform = useDocument((state) => state.snapshot?.scene.scan?.transform ?? null);
  const centroids = useDisplayedCentroids();

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || !matrix || !transform || !centroids) return;
    const mapping = frameMapping(transform, matrix);
    const box = footprint(mapping, centroids);
    if (!box) return;
    const extent = Math.max(
      box.max[0] - box.min[0],
      box.max[1] - box.min[1],
      box.max[2] - box.min[2],
    );
    const length = Math.max(MIN_AXIS_MM, AXIS_SHARE * extent);
    const origin = mapping.toDisplay([0, 0, 0]);
    const axes: [Vec3, string][] = [
      [[length, 0, 0], SCENE_COLORS.axisX],
      [[0, length, 0], SCENE_COLORS.axisY],
      [[0, 0, length], SCENE_COLORS.axisZ],
    ];
    const [x0, y0] = [box.min[0], box.min[1]];
    const [x1, y1] = [box.max[0], box.max[1]];
    const corners: Vec3[] = [
      [x0, y0, 0],
      [x1, y0, 0],
      [x1, y1, 0],
      [x0, y1, 0],
    ].map((corner) => mapping.toDisplay(corner as Vec3));
    const outline = corners.flatMap((corner, index) =>
      segment(corner, corners[(index + 1) % corners.length] ?? corner),
    );

    const overlay = viewport.createOverlay();
    const disposables: { dispose(): void }[] = [];
    const add = (positions: number[], color: string) => {
      const geometry = new BufferGeometry();
      geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
      const material = new LineBasicMaterial({ color, depthTest: false });
      const lines = new LineSegments(geometry, material);
      lines.renderOrder = 10;
      overlay.add(lines);
      disposables.push(geometry, material);
    };
    for (const [tip, color] of axes) add(segment(origin, mapping.toDisplay(tip)), color);
    add(outline, SCENE_COLORS.axisZ);
    viewport.invalidate();
    return () => {
      overlay.dispose();
      disposables.forEach((item) => item.dispose());
      viewport.invalidate();
    };
  }, [matrix, transform, centroids]);
}
