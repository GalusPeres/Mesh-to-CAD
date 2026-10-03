import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { KernelFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { getViewport } from '../../viewport/api';
import { samplePoints } from './edges';

/** Screen radius around each edge sample whose visible scan triangles are fitted. */
const PICK_RADIUS_PX = 12;
const SAMPLES = 24;

export type ScanRadius =
  { status: 'ok'; radius: number; measured: number } | { status: 'tooFewFaces'; count: number };

/**
 * _Radius aus Scan_ (ARCHITECTURE.md 4.5): fit a cylinder to the visible scan triangles
 * along the picked edges and propose its radius, snapped to a design value when the fit
 * found one. `segments` are the picked edges' line segments (6 numbers each).
 */
export async function radiusFromScan(segments: Float32Array): Promise<ScanRadius> {
  const viewport = getViewport();
  const scanKey = viewport?.scan.scanKey;
  if (!viewport || !scanKey) return { status: 'tooFewFaces', count: 0 };
  const faces = new Set<number>();
  for (const point of samplePoints(segments, SAMPLES)) {
    const screen = viewport.worldToScreen(point);
    if (!screen) continue;
    for (const face of viewport.pickScanFacesInCircle(screen, PICK_RADIUS_PX, {
      visibleOnly: true,
    })) {
      faces.add(face);
    }
  }
  if (faces.size < MIN_FIT_FACES) return { status: 'tooFewFaces', count: faces.size };
  const result = await kernel().call(
    'fit.preview',
    {
      faces: Uint32Array.from(faces).sort(),
      scanKey,
      kind: 'cylinder',
      robust: true,
      snap: true,
    },
    { lane: 'fit.preview:fillet' },
  ).result;
  if (result.primitive.type !== 'cylinder') {
    throw new KernelFailure({ code: 'fit.didNotConverge', params: {} });
  }
  const snap = result.snaps.find((item) => item.id === 'radius');
  return {
    status: 'ok',
    radius: snap?.value ?? result.primitive.radius,
    measured: snap?.measured ?? result.primitive.radius,
  };
}
