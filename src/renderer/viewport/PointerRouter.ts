// Routes pointer, wheel and key events of the canvas to the registered
// interactions (viewport chrome first, then tools latest first). An interaction
// that consumes a pointer-down owns the drag until pointer-up, and navigation is
// off meanwhile. Key presses in text fields never reach interactions.

import type { ViewportInteraction, ViewportPointerEvent } from './api';

/** Viewport-internal interactions may also hear that the pointer left the canvas. */
export interface ChromeInteraction extends ViewportInteraction {
  onPointerLeave?(): void;
}

function inTextField(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

export class PointerRouter {
  private readonly interactions: ViewportInteraction[] = [];
  private readonly chrome: ChromeInteraction[] = [];
  private dragOwner: ViewportInteraction | null = null;
  private readonly detach: () => void;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly setNavigationEnabled: (enabled: boolean) => void,
  ) {
    const onPointerDown = (event: PointerEvent) => {
      canvas.focus({ preventScroll: true });
      const viewportEvent = this.toEvent(event);
      const owner = this.ordered().find((interaction) =>
        interaction.onPointerDown?.(viewportEvent),
      );
      if (!owner) return;
      this.dragOwner = owner;
      setNavigationEnabled(false);
      canvas.setPointerCapture(event.pointerId);
      event.preventDefault();
    };
    const onPointerMove = (event: PointerEvent) => {
      const viewportEvent = this.toEvent(event);
      if (this.dragOwner) this.dragOwner.onPointerMove?.(viewportEvent);
      else this.ordered().some((interaction) => interaction.onPointerMove?.(viewportEvent));
    };
    const onPointerUp = (event: PointerEvent) => {
      const owner = this.dragOwner;
      this.dragOwner = null;
      setNavigationEnabled(true);
      owner?.onPointerUp?.(this.toEvent(event));
    };
    const onPointerLeave = () => {
      if (!this.dragOwner) this.chrome.forEach((interaction) => interaction.onPointerLeave?.());
    };
    const onWheel = (event: WheelEvent) => {
      const viewportEvent = { ...this.toEvent(event), deltaY: event.deltaY };
      if (this.ordered().some((interaction) => interaction.onWheel?.(viewportEvent))) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (inTextField(event.target)) return;
      if (this.ordered().some((interaction) => interaction.onKeyDown?.(event))) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const onContextMenu = (event: MouseEvent) => event.preventDefault();

    // Capture phase: interactions see the pointer before the camera rig does.
    canvas.addEventListener('pointerdown', onPointerDown, { capture: true });
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    canvas.addEventListener('pointerleave', onPointerLeave);
    canvas.addEventListener('wheel', onWheel, { capture: true, passive: false });
    canvas.addEventListener('contextmenu', onContextMenu);
    window.addEventListener('keydown', onKeyDown, true);
    this.detach = () => {
      canvas.removeEventListener('pointerdown', onPointerDown, { capture: true });
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('pointercancel', onPointerUp);
      canvas.removeEventListener('pointerleave', onPointerLeave);
      canvas.removeEventListener('wheel', onWheel, { capture: true });
      canvas.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }

  get count(): number {
    return this.interactions.length;
  }

  add(interaction: ViewportInteraction): () => void {
    this.interactions.push(interaction);
    this.updateCursor();
    return () => {
      const index = this.interactions.indexOf(interaction);
      if (index >= 0) this.interactions.splice(index, 1);
      if (this.dragOwner === interaction) {
        this.dragOwner = null;
        this.setNavigationEnabled(true);
      }
      this.updateCursor();
    };
  }

  /** Viewport chrome (view cube): asked before every tool. */
  addChrome(interaction: ChromeInteraction): void {
    this.chrome.push(interaction);
  }

  /** Cursor while the pointer is over viewport chrome; null returns to the tool's cursor. */
  setChromeCursor(cursor: string | null): void {
    if (cursor) this.canvas.style.cursor = cursor;
    else this.updateCursor();
  }

  dispose(): void {
    this.detach();
  }

  private ordered(): ViewportInteraction[] {
    return [...this.chrome, ...[...this.interactions].reverse()];
  }

  private updateCursor(): void {
    const cursor = [...this.interactions]
      .reverse()
      .find((interaction) => interaction.cursor)?.cursor;
    this.canvas.style.cursor = cursor ?? 'default';
  }

  private toEvent(event: PointerEvent | WheelEvent): ViewportPointerEvent {
    const rect = this.canvas.getBoundingClientRect();
    return {
      screen: { x: event.clientX - rect.left, y: event.clientY - rect.top },
      button: event.button,
      buttons: event.buttons,
      ctrl: event.ctrlKey,
      shift: event.shiftKey,
      alt: event.altKey,
    };
  }
}
