// The net in the viewport: its limit surface (heatmap or plain colour), the net lines
// drawn on the surface, the open border, and the control points at their limit
// positions. All four share the dense position buffer of the LimitSurface, so a
// drag updates one array.

import * as THREE from 'three';

import type { Overlay, Vec3 } from '../../viewport/api';
import { NET_COLORS, SCENE_COLORS } from '../../viewport/palette';
import type { LimitSurface } from './limitSurface';

const POINT_SIZE_PX = 9;

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
    overlay.applyDepthBias(surfaceMaterial, 1);
    this.add(new THREE.Mesh(this.surfaceGeometry, surfaceMaterial), surfaceMaterial);

    const inner: number[] = [];
    const border: number[] = [];
    for (let s = 0; s < map.segments.length / 2; s += 1) {
      const target = map.boundaryEdges[map.segmentEdges[s] ?? 0] ? border : inner;
      target.push(map.segments[s * 2] ?? 0, map.segments[s * 2 + 1] ?? 0);
    }
    this.lineGeometry.setAttribute('position', this.position);
    this.lineGeometry.setIndex(inner);
    const lineMaterial = new THREE.LineBasicMaterial({
      color: NET_COLORS.lines,
      transparent: true,
      opacity: 0.75,
    });
    overlay.applyDepthBias(lineMaterial, 1.5);
    this.lines = new THREE.LineSegments(this.lineGeometry, lineMaterial);
    this.add(this.lines, lineMaterial);

    this.borderGeometry.setAttribute('position', this.position);
    this.borderGeometry.setIndex(border);
    const borderMaterial = new THREE.LineBasicMaterial({ color: NET_COLORS.border });
    overlay.applyDepthBias(borderMaterial, 1.5);
    this.add(new THREE.LineSegments(this.borderGeometry, borderMaterial), borderMaterial);

    this.pointColors = new Float32Array(surface.controlCount * 3);
    this.pointGeometry.setAttribute('position', this.position);
    this.pointGeometry.setAttribute('color', new THREE.BufferAttribute(this.pointColors, 3));
    this.pointGeometry.setDrawRange(0, surface.controlCount);
    const pointMaterial = new THREE.PointsMaterial({
      size: POINT_SIZE_PX,
      sizeAttenuation: false,
      vertexColors: true,
      map: this.texture,
      alphaTest: 0.5,
    });
    overlay.applyDepthBias(pointMaterial, 2);
    this.points = new THREE.Points(this.pointGeometry, pointMaterial);
    this.add(this.points, pointMaterial);

    this.setSurfaceColors(null);
    this.paintPoints(new Set(), null);
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

  paintPoints(selected: ReadonlySet<number>, hover: number | null): void {
    const plain = rgb(NET_COLORS.point);
    const chosen = rgb(SCENE_COLORS.selection);
    const hovered = rgb(NET_COLORS.hover);
    for (let i = 0; i < this.surface.controlCount; i += 1) {
      const color = i === hover ? hovered : selected.has(i) ? chosen : plain;
      this.pointColors.set(color, i * 3);
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
