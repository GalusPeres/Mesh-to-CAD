// The scan as tools see it (ScanView) plus its display settings. It outlives the
// individual ScanMesh: display mode, opacity, colour maps and state that arrives
// before its scan is ready are kept here and applied to each new mesh.
//
// Region colours: the document's regions show in the display mode "Bereiche";
// regions a tool sets with setRegions (a segmentation preview) show in every
// mode until the tool passes null, which returns to the document's regions.
// Deviation colours show while the mode is "Abweichung" or the deviation
// display is switched on (viewStore.deviationVisible).

import type * as THREE from 'three';

import type { DisplayMode } from '../state/viewStore';
import type { DeviationDisplay, ScanView } from './api';
import { SCENE_MIX } from './palette';
import { FLAG_HIDDEN, FLAG_HOVER, FLAG_SELECTED, type ScanMesh } from './scanMesh';
import {
  DEVIATION_SCHEMES,
  type ScanMaterials,
  type ScanUniforms,
  createScanMaterials,
  createScanUniforms,
  deviationBoundaries,
  writeRegionColors,
} from './scanMaterial';

/** Triangle edges are drawn only below this face count (docs/DESIGN.md 6.2). */
export const EDGE_DISPLAY_LIMIT = 500_000;

interface Regions {
  labels: Uint16Array;
  colorIndex: Uint8Array;
}

/** What a change affects: only colours, or which faces can be seen (and picked). */
export type ScanChange = 'appearance' | 'visibility';

export class ScanLayer implements ScanView {
  readonly uniforms: ScanUniforms = createScanUniforms();
  readonly materials: ScanMaterials;
  private mesh: ScanMesh | null = null;
  private mode: DisplayMode = 'shaded';
  private deviationVisible = false;
  private opacity = 1;
  private tolerance = 0.1;
  private documentRegions: Regions | null = null;
  private toolRegions: Regions | null = null;
  private shownLabels: Uint16Array | null = null;
  private deviationValues: Float32Array | null = null;
  private deviationDisplay: DeviationDisplay | null = null;
  private deviationApplied = false;
  private hovered: Uint32Array | null = null;
  private stateFaces: Uint32Array | null = null;
  private pendingSelection: Uint8Array | null = null;
  private pendingHidden: Uint8Array | null = null;

  constructor(
    clipping: THREE.Plane[],
    private readonly changed: (change: ScanChange) => void,
  ) {
    this.materials = createScanMaterials(this.uniforms, clipping);
  }

  get current(): ScanMesh | null {
    return this.mesh;
  }

  get faceCount(): number {
    return this.mesh?.faceCount ?? 0;
  }

  get scanKey(): string | null {
    return this.mesh?.scanKey ?? null;
  }

  /** Show a new mesh. State of the same scan is carried over, other state is dropped. */
  attach(mesh: ScanMesh | null): void {
    const previous = this.mesh;
    const sameScan = !!mesh && !!previous && previous.scanKey === mesh.scanKey;
    if (mesh && previous && sameScan) mesh.copyStateFrom(previous);
    if (!sameScan) {
      this.hovered = null;
      this.stateFaces = null;
      this.toolRegions = null;
      this.deviationValues = null;
    }
    this.mesh = mesh;
    this.shownLabels = null;
    this.deviationApplied = false;
    if (mesh) {
      mesh.setMaterial(this.material());
      if (this.pendingSelection?.length === mesh.faceCount)
        this.setSelection(this.pendingSelection);
      if (this.pendingHidden?.length === mesh.faceCount) this.setHidden(this.pendingHidden);
      this.pendingSelection = null;
      this.pendingHidden = null;
    }
    this.updateRegions();
    this.updateDeviation();
    this.changed('visibility');
  }

  /** The topology (vertex indices) arrived: deviation values can be spread now. */
  topologyReady(): void {
    this.updateDeviation();
  }

  setDisplay(mode: DisplayMode, deviationVisible: boolean, edgeColor: string): void {
    this.mode = mode;
    this.deviationVisible = deviationVisible;
    this.uniforms.uEdgeColor.value.set(edgeColor);
    this.uniforms.uFlat.value = mode === 'flat' ? 1 : 0;
    this.uniforms.uEdges.value =
      mode === 'shadedEdges' && this.faceCount < EDGE_DISPLAY_LIMIT ? 1 : 0;
    this.mesh?.setMaterial(this.material());
    this.updateRegions();
    this.updateDeviation();
    this.changed('appearance');
  }

  setTolerance(tolerance: number): void {
    this.tolerance = tolerance > 0 ? tolerance : 0.1;
  }

  setDocumentRegions(labels: Uint16Array | null, colorIndex: Uint8Array | null): void {
    this.documentRegions = labels && colorIndex ? { labels, colorIndex } : null;
    this.shownLabels = null;
    this.updateRegions();
  }

  // ScanView ----------------------------------------------------------------------

  setSelection(mask: Uint8Array): void {
    const mesh = this.mesh;
    if (!mesh || mask.length !== mesh.faceCount) {
      this.pendingSelection = mask;
      return;
    }
    mesh.setFlagForAll(FLAG_SELECTED, (face) => mask[face] !== 0);
    this.changed('appearance');
  }

  updateSelection(faces: Uint32Array, selected: boolean): void {
    this.mesh?.setFlagForFaces(faces, FLAG_SELECTED, selected);
    this.changed('appearance');
  }

  setHover(faces: Uint32Array | null): void {
    const mesh = this.mesh;
    if (!mesh) return;
    if (this.hovered) mesh.setFlagForFaces(this.hovered, FLAG_HOVER, false);
    if (faces) mesh.setFlagForFaces(faces, FLAG_HOVER, true);
    this.hovered = faces;
    this.changed('appearance');
  }

  setHidden(mask: Uint8Array | null): void {
    const mesh = this.mesh;
    if (mask && (!mesh || mask.length !== mesh.faceCount)) {
      this.pendingHidden = mask;
      return;
    }
    mesh?.setFlagForAll(FLAG_HIDDEN, (face) => !!mask && mask[face] !== 0);
    this.changed('visibility');
  }

  setFaceStates(faces: Uint32Array | null, states?: Uint8Array): void {
    const mesh = this.mesh;
    if (!mesh) return;
    if (this.stateFaces) mesh.setStates(this.stateFaces, null);
    if (faces) mesh.setStates(faces, states ?? null);
    this.stateFaces = faces;
    this.changed('appearance');
  }

  setRegions(labels: Uint16Array | null, colorIndex: Uint8Array | null): void {
    this.toolRegions = labels && colorIndex ? { labels, colorIndex } : null;
    this.shownLabels = null;
    this.updateRegions();
  }

  setDeviation(values: Float32Array | null, display?: DeviationDisplay): void {
    this.deviationValues = values;
    if (display) this.deviationDisplay = display;
    this.deviationApplied = false;
    this.updateDeviation();
  }

  setOpacity(opacity: number): void {
    this.opacity = Math.min(1, Math.max(0, opacity));
    this.mesh?.setMaterial(this.material());
    this.changed('appearance');
  }

  // --------------------------------------------------------------------------------

  private material(): THREE.MeshStandardMaterial {
    const xray = this.mode === 'xray';
    const opacity = Math.min(this.opacity, xray ? SCENE_MIX.xrayOpacity : 1);
    if (opacity >= 1) return this.materials.opaque;
    this.materials.transparent.opacity = opacity;
    return this.materials.transparent;
  }

  private updateRegions(): void {
    const regions = this.toolRegions ?? (this.mode === 'regions' ? this.documentRegions : null);
    const mesh = this.mesh;
    const usable = !!regions && !!mesh && regions.labels.length === mesh.faceCount;
    if (usable && regions.labels !== this.shownLabels) {
      const texture = this.uniforms.uRegionColors.value;
      writeRegionColors(texture.image.data as Uint8Array, regions.colorIndex);
      texture.needsUpdate = true;
      mesh.setRegionLabels(regions.labels);
      this.shownLabels = regions.labels;
    }
    this.uniforms.uRegionsOn.value = usable ? 1 : 0;
    this.changed('appearance');
  }

  private updateDeviation(): void {
    const mesh = this.mesh;
    const values = this.deviationValues;
    if (mesh && values && !this.deviationApplied) this.deviationApplied = mesh.setDeviation(values);
    const display = this.deviationDisplay ?? {
      tolerance: this.tolerance,
      range: this.tolerance * 3,
      scheme: 'standard' as const,
    };
    const tolerance = display.tolerance > 0 ? display.tolerance : this.tolerance;
    const range = display.range > tolerance ? display.range : tolerance * 3;
    this.uniforms.uBounds.value = deviationBoundaries(tolerance, range);
    this.uniforms.uScheme.value = Math.max(0, DEVIATION_SCHEMES.indexOf(display.scheme));
    const wanted = this.mode === 'deviation' || this.deviationVisible;
    this.uniforms.uDeviationOn.value = wanted && !!values && this.deviationApplied ? 1 : 0;
    this.changed('appearance');
  }
}
