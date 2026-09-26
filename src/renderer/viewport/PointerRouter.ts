// Routes pointer, wheel and key events of the canvas to the registered
// interactions (selection modes, tool handlers, handles), latest first. An
// interaction that consumes a pointer-down owns the drag until pointer-up, and
// navigation is off meanwhile.

import type { ViewportInteraction, ViewportPointerEvent } from './api';

export class PointerRouter {
  private readonly interactions: ViewportInteraction[] = [];
  private dragOwner: ViewportInteraction | null = null;
  private readonly detach: () => void;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly setNavigationEnabled: (enabled: boolean) => void,
  ) {
    const onPointerDown = (event: PointerEvent) => {
      canvas.focus();
      const viewportEvent = this.toEvent(event);
      const owner = this.topDown().find((interaction) =>
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
      else this.topDown().some((interaction) => interaction.onPointerMove?.(viewportEvent));
    };
    const onPointerUp = (event: PointerEvent) => {
      const owner = this.dragOwner;
      this.dragOwner = null;
      setNavigationEnabled(true);
      owner?.onPointerUp?.(this.toEvent(event));
    };
    const onWheel = (event: WheelEvent) => {
      const viewportEvent = { ...this.toEvent(event), deltaY: event.deltaY };
      if (this.topDown().some((interaction) => interaction.onWheel?.(viewportEvent))) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (this.topDown().some((interaction) => interaction.onKeyDown?.(event))) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const onContextMenu = (event: MouseEvent) => event.preventDefault();

    // Capture phase: interactions see the pointer before the orbit controls do.
    canvas.addEventListener('pointerdown', onPointerDown, { capture: true });
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('wheel', onWheel, { capture: true, passive: false });
    canvas.addEventListener('contextmenu', onContextMenu);
    window.addEventListener('keydown', onKeyDown, true);
    this.detach = () => {
      canvas.removeEventListener('pointerdown', onPointerDown, { capture: true });
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerup', onPointerUp);
      canvas.removeEventListener('wheel', onWheel, { capture: true });
      canvas.removeEventListener('contextmenu', onContextMenu);
      window.removeEventListener('keydown', onKeyDown, true);
    };
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

  dispose(): void {
    this.detach();
  }

  private topDown(): ViewportInteraction[] {
    return [...this.interactions].reverse();
  }

  private updateCursor(): void {
    const cursor = this.topDown().find((interaction) => interaction.cursor)?.cursor;
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
