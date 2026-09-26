import type { PointerEvent } from 'react';

import styles from './Splitter.module.css';

export interface SplitterProps {
  /** Which neighbour the splitter resizes. */
  side: 'left' | 'right';
  width: number;
  min: number;
  max: number;
  label: string;
  onResize: (width: number) => void;
}

/** A 1 px line with a 5 px grab area between a side panel and the viewport. */
export function Splitter({ side, width, min, max, label, onResize }: SplitterProps) {
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    const start = event.clientX;
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const onMove = (move: globalThis.PointerEvent) => {
      const delta = side === 'left' ? move.clientX - start : start - move.clientX;
      onResize(Math.min(max, Math.max(min, width + delta)));
    };
    const onUp = () => {
      target.removeEventListener('pointermove', onMove);
      target.removeEventListener('pointerup', onUp);
    };
    target.addEventListener('pointermove', onMove);
    target.addEventListener('pointerup', onUp);
  };
  return (
    <div
      className={styles.splitter}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      onPointerDown={onPointerDown}
    />
  );
}
