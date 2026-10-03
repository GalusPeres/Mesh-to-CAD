import { Blend, Box, Eye, Maximize2, SquareSplitHorizontal, View } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { formatShortcut } from '../app/commands/keymap';
import {
  type Visibility,
  setDisplayMode,
  setProjection,
  setVisibility,
  useView,
} from '../state/viewStore';
import { IconButton } from '../ui/IconButton/IconButton';
import { Menu, MenuItem } from '../ui/Menu/Menu';
import { getViewport, useViewport } from './api';
import { EDGE_DISPLAY_LIMIT } from './scanLayer';
import { DISPLAY_MODES, STANDARD_VIEW_KEYS } from './view.commands';
import { toggleSectionPlane, toggleXray } from './viewActions';

const VISIBILITIES: readonly Visibility[] = ['both', 'scan', 'bodies'];

/** The view group at the right end of the tool row, present in every stage. */
export function ViewToolGroup() {
  const { t, i18n } = useTranslation('viewport');
  const viewport = useViewport();
  const projection = useView((state) => state.projection);
  const visibility = useView((state) => state.visibility);
  const sectionOn = useView((state) => state.sectionPlane !== null);
  const displayMode = useView((state) => state.displayMode);
  const perspective = projection === 'perspective';
  const key = (shortcut: string, shift = false) =>
    formatShortcut({ key: shortcut, shift }, i18n.language);

  return (
    <>
      <IconButton
        icon={Maximize2}
        label={t('commands.fitAll')}
        shortcut={key('F')}
        disabled={!viewport}
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
        {STANDARD_VIEW_KEYS.map(([view, shortcut]) => (
          <MenuItem
            key={view}
            label={t(`views.${view}`)}
            shortcut={key(shortcut)}
            onSelect={() => getViewport()?.camera.setStandardView(view)}
          />
        ))}
      </Menu>
      <IconButton
        icon={Box}
        label={t('commands.perspective')}
        shortcut={key('P')}
        pressed={perspective}
        data-testid="tool-view-perspective"
        onClick={() => setProjection(perspective ? 'orthographic' : 'perspective')}
      />
      <Menu
        align="end"
        trigger={
          <IconButton
            icon={Eye}
            label={`${t('visibility.label')}: ${t(`visibility.${visibility}`)}`}
            shortcut={key(' ')}
            data-testid="tool-view-visibility"
          />
        }
      >
        {VISIBILITIES.map((option) => (
          <MenuItem
            key={option}
            label={t(`visibility.${option}`)}
            checked={visibility === option}
            onSelect={() => setVisibility(option)}
          />
        ))}
      </Menu>
      <IconButton
        icon={SquareSplitHorizontal}
        label={t('commands.sectionPlane')}
        pressed={sectionOn}
        disabled={!viewport}
        data-testid="tool-view-section"
        onClick={toggleSectionPlane}
      />
      <Menu
        align="end"
        trigger={
          <IconButton icon={Blend} label={t('display.label')} data-testid="tool-view-display" />
        }
      >
        {DISPLAY_MODES.map((mode) => (
          <MenuItem
            key={mode}
            label={t(`display.${mode}`)}
            shortcut={mode === 'xray' ? key('X') : undefined}
            checked={displayMode === mode}
            disabled={
              mode === 'shadedEdges' && (viewport?.scan.faceCount ?? 0) >= EDGE_DISPLAY_LIMIT
            }
            onSelect={() => (mode === 'xray' ? toggleXray() : setDisplayMode(mode))}
          />
        ))}
      </Menu>
    </>
  );
}
