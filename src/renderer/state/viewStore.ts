import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

export type Projection = 'orthographic' | 'perspective';
export type DisplayMode =
  'shaded' | 'shadedEdges' | 'flat' | 'xray' | 'regions' | 'deviation' | 'covered';
export type Visibility = 'scan' | 'bodies' | 'both';

/** A clipping plane in part coordinates; the side the normal points to is cut away. */
export interface SectionPlane {
  origin: readonly [number, number, number];
  normal: readonly [number, number, number];
}

export interface ViewState {
  projection: Projection;
  displayMode: DisplayMode;
  /** What is drawn: the scan, the bodies or both (Space cycles through them). */
  visibility: Visibility;
  deviationVisible: boolean;
  sectionPlane: SectionPlane | null;
}

export const viewStore = createStore<ViewState>(() => ({
  projection: 'orthographic',
  displayMode: 'shaded',
  visibility: 'both',
  deviationVisible: false,
  sectionPlane: null,
}));

export function useView<T>(selector: (state: ViewState) => T): T {
  return useStore(viewStore, selector);
}

export function setProjection(projection: Projection): void {
  viewStore.setState({ projection });
}

export function setDisplayMode(displayMode: DisplayMode): void {
  viewStore.setState({ displayMode });
}

export function setVisibility(visibility: Visibility): void {
  viewStore.setState({ visibility });
}

export function setSectionPlane(sectionPlane: SectionPlane | null): void {
  viewStore.setState({ sectionPlane });
}
