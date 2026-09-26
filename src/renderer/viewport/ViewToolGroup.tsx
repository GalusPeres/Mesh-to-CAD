import { Box, Maximize2, View } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatShortcut } from '../app/commands/keymap';
import { setProjection, useView } from '../state/viewStore';
import { IconButton } from '../ui/IconButton/IconButton';
import { Menu, MenuItem } from '../ui/Menu/Menu';
import { type StandardView, getViewport } from './api';

const VIEWS: readonly [StandardView, string][] = [
  ['front', '1'],
  ['back', '2'],
  ['left', '3'],
  ['right', '4'],
  ['top', '5'],
  ['bottom', '6'],
  ['iso', '0'],
];

/** The view group at the right end of the tool row, present in every stage. */
export function ViewToolGroup() {
  const { t, i18n } = useTranslation('viewport');
  const projection = useView((state) => state.projection);
  const perspective = projection === 'perspective';
  return (
    <>
      <IconButton
        icon={Maximize2}
        label={t('commands.fitAll')}
        shortcut="F"
        data-testid="tool-view-fit-all"
        onClick={() => getViewport()?.camera.fitAll()}
      />
      <Menu
        align="end"
        trigger={
          <IconButton
            icon={View}
            label={t('commands.standardViews')}
            data-testid="tool-view-standard"
          />
        }
      >
        {VIEWS.map(([view, key]) => (
          <MenuItem
            key={view}
            label={t(`views.${view}`)}
            shortcut={formatShortcut({ key }, i18n.language)}
            onSelect={() => getViewport()?.camera.setStandardView(view)}
          />
        ))}
      </Menu>
      <IconButton
        icon={Box}
        label={t('commands.perspective')}
        shortcut="P"
        pressed={perspective}
        onClick={() => setProjection(perspective ? 'orthographic' : 'perspective')}
      />
    </>
  );
}
