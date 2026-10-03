// The net in the viewport: its limit surface (heatmap or plain colour, and faintly
// where the scan covers it), the net lines
// drawn on the surface, the outlines of the CAD faces it becomes (patch layout and
// open border, in white), and the control points at their limit positions. All four
// share the dense position buffer of the LimitSurface, so a drag updates one array.

import * as THREE from 'three';

import type { Overlay, Vec3 } from '../../viewport/api';
import { NET_COLORS, SCENE_COLORS } from '../../viewport/palette';
import type { LimitSurface } from './limitSurface';

const POINT_SIZE_PX = 7;
/** Opacity of the surface where the scan covers it (a row over a rounding runs inside). */
const GHOST_OPACITY = 0.35;
/** Depth bias of the surface in units of the scene bias (bodies use 1). */
const SURFACE_BIAS = 4;

function circleTexture(): THREE.Texture {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  if (context) {
    // A disc; the vertex colour tints it (plain, selected, hovered).
    context.beginPath();
    context.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    context.fillStyle = NET_COLORS.pointRing;
    context.fill();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function rgb(hex: string): [number, number, number] {
  const color = new THREE.Color(hex);
  return [color.r, color.g, color.b];
}

export class NetOverlay {
  private readonly position: THREE.BufferAttribute;
  private readonly surfaceGeometry = new THREE.BufferGeometry();
  private readonly surfaceColors: Float32Array;
  private readonly lineGeometry = new THREE.BufferGeometry();
  private readonly borderGeometry = new THREE.BufferGeometry();
  private readonly pointGeometry = new THREE.BufferGeometry();
  private readonly pointColors: Float32Array;
  private readonly materials: THREE.Material[] = [];
  private readonly texture = circleTexture();
  private readonly points: THREE.Points;
  private readonly lines: THREE.LineSegments;

  constructor(
    private readonly overlay: Overlay,
    private readonly surface: LimitSurface,
  ) {
    const { map } = surface;
    this.position = new THREE.BufferAttribute(surface.positions, 3);
    this.position.setUsage(THREE.DynamicDrawUsage);

    this.surfaceColors = new Float32Array(surface.fineCount * 3);
    this.surfaceGeometry.setAttribute('position', this.position);
    this.surfaceGeometry.setAttribute('color', new THREE.BufferAttribute(this.surfaceColors, 3));
    this.surfaceGeometry.setIndex(new THREE.BufferAttribute(map.triangles, 1));
    this.surfaceGeometry.computeVertexNormals();
    const surfaceMaterial = new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 0.55,
      metalness: 0,
    });
    // Drawn in front of the scan wherever it lies within a few tolerances of it, also
    // where it runs slightly inside the scan's ridges (else the scan shows through).
    overlay.applyDepthBias(surfaceMaterial, SURFACE_BIAS);
    // Where the surface runs inside the scan it still shows, faintly, in its heatmap
    // colours: drawn first without depth test, then covered by the surface where visible.
    const ghostMaterial = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: GHOST_OPACITY,
      depthTest: false,
      depthWrite: false,
      side: THREE.FrontSide,
    });
    const ghost = new THREE.Mesh(this.surfaceGeometry, ghostMaterial);
    ghost.renderOrder = 20;
    this.add(ghost, ghostMaterial);
    const shaded = new THREE.Mesh(this.surfaceGeometry, surfaceMaterial);
    shaded.renderOrder = 21;
    this.add(shaded, surfaceMaterial);

    const inner: number[] = [];
    const border: number[] = [];
    for (let s = 0; s < map.segments.length / 2; s += 1) {
      const edge = map.segmentEdges[s] ?? 0;
      const target = map.boundaryEdges[edge] || map.faceEdges[edge] ? border : inner;
      target.push(map.segments[s * 2] ?? 0, map.segments[s * 2 + 1] ?? 0);
    }
    this.lineGeometry.setAttribute('position', this.position);
    this.lineGeometry.setIndex(inner);
    const lineMaterial = new THREE.LineBasicMaterial({
      color: NET_COLORS.lines,
      transparent: true,
      opacity: 0.45,
    });
    overlay.applyDepthBias(lineMaterial, SURFACE_BIAS + 0.5);
    this.lines = new THREE.LineSegments(this.lineGeometry, lineMaterial);
    this.add(this.lines, lineMaterial);

    this.borderGeometry.setAttribute('position', this.position);
    this.borderGeometry.setIndex(border);
    const borderMaterial = new THREE.LineBasicMaterial({ color: NET_COLORS.border });
    overlay.applyDepthBias(borderMaterial, SURFACE_BIAS + 0.5);
    this.add(new THREE.LineSegments(this.borderGeometry, borderMaterial), borderMaterial);

    // RGBA: points away from the pointer get alpha 0 and are discarded by the alpha test.
    this.pointColors = new Float32Array(surface.controlCount * 4);
    this.pointGeometry.setAttribute('position', this.position);
    this.pointGeometry.setAttribute('color', new THREE.BufferAttribute(this.pointColors, 4));
    this.pointGeometry.setDrawRange(0, surface.controlCount);
    const pointMaterial = new THREE.PointsMaterial({
      size: POINT_SIZE_PX,
      sizeAttenuation: false,
      vertexColors: true,
      map: this.texture,
      alphaTest: 0.5,
    });
    overlay.applyDepthBias(pointMaterial, SURFACE_BIAS + 1);
    this.points = new THREE.Points(this.pointGeometry, pointMaterial);
    this.add(this.points, pointMaterial);

    this.setSurfaceColors(null);
    this.paintPoints(new Set(), null, () => false);
  }

  /** The dense positions changed (all of them, or the given rows). */
  positionsChanged(): void {
    this.position.needsUpdate = true;
    this.surfaceGeometry.computeVertexNormals();
  }

  /** Heatmap colours (RGB per dense vertex), or null for the plain net colour. */
  setSurfaceColors(colors: Float32Array | null): void {
    if (colors) this.surfaceColors.set(colors);
    else {
      const [r, g, b] = rgb(NET_COLORS.surface);
      for (let i = 0; i < this.surfaceColors.length; i += 3) {
        this.surfaceColors[i] = r;
        this.surfaceColors[i + 1] = g;
        this.surfaceColors[i + 2] = b;
      }
    }
    (this.surfaceGeometry.getAttribute('color') as THREE.BufferAttribute).needsUpdate = true;
  }

  /**
   * Colour the control points: hovered, chosen, irregular (a warning, as in
   * QuickSurface) or plain. Only chosen, irregular and hovered points and those `shown`
   * (near the pointer) are drawn, so a dense net does not cover its heatmap with dots.
   */
  paintPoints(
    selected: ReadonlySet<number>,
    hover: number | null,
    shown: (control: number) => boolean,
    irregular: ReadonlySet<number> = new Set(),
  ): void {
    const plain = rgb(NET_COLORS.point);
    const chosen = rgb(SCENE_COLORS.selection);
    const hovered = rgb(NET_COLORS.hover);
    const warning = rgb(NET_COLORS.irregular);
    for (let i = 0; i < this.surface.controlCount; i += 1) {
      const isChosen = selected.has(i);
      const isIrregular = irregular.has(i);
      const color = i === hover ? hovered : isChosen ? chosen : isIrregular ? warning : plain;
      this.pointColors.set(color, i * 4);
      this.pointColors[i * 4 + 3] = i === hover || isChosen || isIrregular || shown(i) ? 1 : 0;
    }
    (this.pointGeometry.getAttribute('color') as THREE.BufferAttribute).needsUpdate = true;
  }

  setNetVisible(visible: boolean): void {
    this.points.visible = visible;
    this.lines.visible = visible;
  }

  /** Unit surface normal at dense vertex i (the limit point of control point i). */
  normalAt(i: number): Vec3 {
    const normals = this.surfaceGeometry.getAttribute('normal') as THREE.BufferAttribute;
    return [normals.getX(i), normals.getY(i), normals.getZ(i)];
  }

  dispose(): void {
    this.overlay.dispose();
    this.surfaceGeometry.dispose();
    this.lineGeometry.dispose();
    this.borderGeometry.dispose();
    this.pointGeometry.dispose();
    this.materials.forEach((material) => material.dispose());
    this.texture.dispose();
  }

  private add(object: THREE.Object3D, material: THREE.Material): void {
    object.frustumCulled = false;
    object.raycast = () => undefined;
    this.materials.push(material);
    this.overlay.add(object);
  }
}
