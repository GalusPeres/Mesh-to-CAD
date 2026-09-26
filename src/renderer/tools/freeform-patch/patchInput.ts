import { useEffect, useState } from 'react';

import type { RegionsPayload } from '@shared/protocol/generated/document-display';

import { kernel } from '../../kernel/kernel';
import { replaceSelection, selectedFaces } from '../../selection/api';
import { documentStore } from '../../state/documentStore';

/** Smoothing weights of the P-spline penalty offered in the panel. */
export const SMOOTHING_LEVELS = { low: 1e-5, medium: 1e-4, high: 1e-3 } as const;
export type SmoothingLevel = keyof typeof SMOOTHING_LEVELS;

/** Span limits of the kernel (`freeform/heightfield.py` MIN_SPANS, MAX_SPANS). */
export const SPAN_RANGE = { min: 2, max: 64 } as const;
export const DEFAULT_SPANS: [number, number] = [16, 12];
export const DEFAULT_MARGIN_MM = 2;

const LEVELS: readonly SmoothingLevel[] = ['low', 'medium', 'high'];

/** The offered level closest to a stored smoothing weight (on a log scale). */
export function smoothingLevel(value: number): SmoothingLevel {
  const distance = (level: SmoothingLevel) =>
    Math.abs(Math.log10(SMOOTHING_LEVELS[level]) - Math.log10(Math.max(value, 1e-12)));
  return LEVELS.reduce((best, level) => (distance(level) < distance(best) ? level : best));
}

export function clampSpans(value: number): number {
  return Math.min(SPAN_RANGE.max, Math.max(SPAN_RANGE.min, Math.round(value)));
}

/** Face indices of a region, read from the regions payload of the scene. */
export async function regionFaces(regionsKey: string, label: number): Promise<Uint32Array> {
  const { payloads } = await kernel().call('scene.fetch', { keys: [regionsKey] }).result;
  const payload = payloads.find((item): item is RegionsPayload => item.type === 'regions');
  if (!payload) return new Uint32Array();
  const faces: number[] = [];
  payload.labels.forEach((value, face) => {
    if (value === label) faces.push(face);
  });
  return Uint32Array.from(faces);
}

/**
 * While a freeform feature is edited, its stored triangles are the working selection;
 * the previous selection returns when the tool closes (docs/DESIGN.md 5.1).
 * Returns false until the stored triangles are loaded.
 */
export function useEditedFeatureFaces(editTarget: string | null): boolean {
  const [ready, setReady] = useState(editTarget === null);
  useEffect(() => {
    if (!editTarget) return;
    const scan = documentStore.getState().snapshot?.document.scan;
    if (!scan) return;
    const previous = selectedFaces(scan.key);
    let current = true;
    kernel()
      .call('freeform.featureFaces', { featureId: editTarget })
      .result.then(({ faces, scanKey }) => {
        if (!current) return;
        if (faces && scanKey === scan.key) replaceSelection(scan.key, scan.faceCount, faces);
        setReady(true);
      })
      .catch(() => {
        if (current) setReady(true);
      });
    return () => {
      current = false;
      replaceSelection(scan.key, scan.faceCount, previous);
    };
  }, [editTarget]);
  return ready;
}
