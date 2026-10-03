import type { ViewportOverlay } from '../../app/extensions';
import styles from './SketchPanel.module.css';
import { useSketchSession } from './sketchSession';

/** Sketch mode caption at the top left of the viewport: "Skizze 1 · Ebene XY". */
function SketchCaption() {
  const active = useSketchSession((state) => state.active);
  const caption = useSketchSession((state) => state.caption);
  if (!active || !caption) return null;
  return (
    <div className={styles.caption} data-testid="sketch-caption">
      {caption}
    </div>
  );
}

export const overlay: ViewportOverlay = { anchor: 'top-left', order: 10, Component: SketchCaption };
