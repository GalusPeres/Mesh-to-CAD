import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../../app/status/types';
import { profileText } from './describe';
import { useSketchSession } from './sketchSession';

/** In sketch mode: what the mouse does and the profile state (DESIGN.md 7.3). */
function SketchModeStatus() {
  const { t } = useTranslation('tools');
  const active = useSketchSession((state) => state.active);
  const profile = useSketchSession((state) => state.profile);
  if (!active) return null;
  const entities = profile ? profile.loops.length + profile.openEntities.length : 0;
  return (
    <span data-testid="status-sketch">
      {t('sectionSketch.statusHint')} · {profileText(profile, entities, t)}
    </span>
  );
}

export const statusItem: StatusItem = { order: 5, Component: SketchModeStatus };
