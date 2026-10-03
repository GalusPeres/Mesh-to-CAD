import { useEffect } from 'react';

import { setToolInfoProvider } from '../../automation/toolInfo';
import type { FeatureGroup } from './model';
import type { Recognition } from './useRecognition';

/**
 * What the open recognition tells automation clients: whether it is still reading
 * the scan, and the groups as the panel lists them, checked or not, with their
 * top-edge rounding switched on or off.
 */
export function useRecognitionInfo(
  recognition: Recognition,
  groups: readonly FeatureGroup[],
  checked: ReadonlySet<number>,
  sharp: ReadonlySet<number>,
): void {
  useEffect(
    () =>
      setToolInfoProvider(() => ({
        state: { job: recognition.status === 'computing' },
        groups: groups.map((group) => ({
          id: group.id,
          role: group.role,
          shape: group.feature.shape,
          params: group.feature.params,
          height: group.feature.height,
          top: group.feature.top,
          tilt: group.feature.tilt,
          rounding: group.feature.rounding,
          count: group.indices.length,
          checked: checked.has(group.id),
          rounded: !sharp.has(group.id),
        })),
      })),
    [recognition.status, groups, checked, sharp],
  );
}
