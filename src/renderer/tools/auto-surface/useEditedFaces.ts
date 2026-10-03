import { useEffect, useState } from 'react';

import { kernel } from '../../kernel/kernel';
import { replaceSelection, selectedFaces } from '../../selection/api';
import { documentStore } from '../../state/documentStore';

/**
 * While an auto surface of selected triangles is edited, its stored triangles are the
 * working selection; the previous selection returns when the tool closes
 * (docs/DESIGN.md 5.1). `ready` is false until the stored triangles are loaded;
 * `hasFaces` tells whether the feature was made from a selection.
 */
export function useEditedFaces(editTarget: string | null): { ready: boolean; hasFaces: boolean } {
  const [state, setState] = useState({ ready: editTarget === null, hasFaces: false });
  useEffect(() => {
    if (!editTarget) return;
    const scan = documentStore.getState().snapshot?.document.scan;
    if (!scan) return;
    const previous = selectedFaces(scan.key);
    let current = true;
    kernel()
      .call('surfacing.featureFaces', { featureId: editTarget })
      .result.then(({ faces, scanKey }) => {
        if (!current) return;
        const stored = faces !== null && scanKey === scan.key;
        if (stored) replaceSelection(scan.key, scan.faceCount, faces);
        setState({ ready: true, hasFaces: stored });
      })
      .catch(() => {
        if (current) setState({ ready: true, hasFaces: false });
      });
    return () => {
      current = false;
      replaceSelection(scan.key, scan.faceCount, previous);
    };
  }, [editTarget]);
  return state;
}
