// The view cube (docs/DESIGN.md 6.7): 88 px in the top right corner, drawn into a
// scissored corner of the viewport's WebGL context with its own scene and camera.
// Each face is split into 3 x 3 pieces; a piece belongs to one of the 26 zones
// (6 faces, 12 edges, 8 corners), and hovering a zone lights all its pieces.

import * as THREE from 'three';

import type { Vec3 } from './api';
import type { ThemeColors } from './displayItems';
import { CUBE_FACES, ZONE_BAND, cubePieces, faceRight } from './viewCubeMath';

export const VIEW_CUBE_PX = 88;
export const CORNER_MARGIN_PX = 8;
/** View cube face labels are the only text below 12 px (docs/DESIGN.md 2.2). */
const LABEL_PX = 11;
const LABEL_TEXTURE_PX = 128;
/** Frustum half size: the cube's bounding sphere with a small margin. */
const FRUSTUM = Math.sqrt(3) * 1.04;

export type CubeLabels = Record<(typeof CUBE_FACES)[number]['label'], string>;

const zoneKey = (zone: Vec3) => zone.join(',');

/** Rotation that turns a plane facing +Z into the face, label upright. */
function orientation(face: (typeof CUBE_FACES)[number]): THREE.Matrix4 {
  return new THREE.Matrix4().makeBasis(
    new THREE.Vector3().fromArray(faceRight(face)),
    new THREE.Vector3().fromArray(face.up),
    new THREE.Vector3().fromArray(face.normal),
  );
}

export class ViewCube {
  readonly scene = new THREE.Scene();
  readonly camera = new THREE.OrthographicCamera(-FRUSTUM, FRUSTUM, FRUSTUM, -FRUSTUM, 0.1, 10);
  private readonly pieces: THREE.Mesh<THREE.PlaneGeometry, THREE.MeshBasicMaterial>[] = [];
  private readonly labelMaterials = new Map<string, THREE.MeshBasicMaterial>();
  private readonly edges: THREE.LineSegments<THREE.EdgesGeometry, THREE.LineBasicMaterial>;
  private readonly raycaster = new THREE.Raycaster();
  private hovered: string | null = null;
  private theme: ThemeColors;
  private labels: CubeLabels | null = null;

  constructor(theme: ThemeColors) {
    this.theme = theme;
    this.build();
    this.edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(2, 2, 2)),
      new THREE.LineBasicMaterial({ color: theme.borderStrong }),
    );
    this.scene.add(this.edges);
    this.camera.up.set(0, 0, 1);
    this.applyTheme();
  }

  /** Screen rectangle in CSS pixels (top left origin) for a viewport of this size. */
  static rect(width: number): { x: number; y: number; size: number } {
    return { x: width - CORNER_MARGIN_PX - VIEW_CUBE_PX, y: CORNER_MARGIN_PX, size: VIEW_CUBE_PX };
  }

  setTheme(theme: ThemeColors): void {
    this.theme = theme;
    this.applyTheme();
  }

  setLabels(labels: CubeLabels): void {
    this.labels = labels;
    this.drawLabels();
  }

  /** Point the cube camera like the main camera. */
  follow(quaternion: THREE.Quaternion): void {
    const back = new THREE.Vector3(0, 0, 1).applyQuaternion(quaternion);
    this.camera.position.copy(back.multiplyScalar(4));
    this.camera.quaternion.copy(quaternion);
    this.camera.updateMatrixWorld();
  }

  /** The zone under a point given in normalised device coordinates of the cube area. */
  zoneAt(ndc: THREE.Vector2): Vec3 | null {
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = this.raycaster.intersectObjects(this.pieces, false)[0];
    return (hit?.object.userData.zone as Vec3 | undefined) ?? null;
  }

  /** Light the pieces of a zone; returns whether anything changed. */
  setHover(zone: Vec3 | null): boolean {
    const key = zone ? zoneKey(zone) : null;
    if (key === this.hovered) return false;
    this.hovered = key;
    this.applyTheme();
    return true;
  }

  dispose(): void {
    this.scene.traverse((node) => {
      const mesh = node as THREE.Mesh;
      mesh.geometry?.dispose();
      const material = mesh.material as THREE.MeshBasicMaterial | undefined;
      material?.map?.dispose();
      material?.dispose();
    });
  }

  private build(): void {
    for (const piece of cubePieces()) {
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(piece.width, piece.height),
        new THREE.MeshBasicMaterial({ side: THREE.FrontSide }),
      );
      mesh.quaternion.setFromRotationMatrix(orientation(piece.face));
      mesh.position.set(...piece.center);
      mesh.userData.zone = piece.zone;
      this.pieces.push(mesh);
      this.scene.add(mesh);
    }
    const inner = 1 - ZONE_BAND;
    for (const face of CUBE_FACES) {
      const label = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false });
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2 * inner, 2 * inner), label);
      mesh.quaternion.setFromRotationMatrix(orientation(face));
      mesh.position.fromArray(face.normal).multiplyScalar(1.001);
      mesh.raycast = () => undefined;
      this.labelMaterials.set(face.label, label);
      this.scene.add(mesh);
    }
  }

  private applyTheme(): void {
    for (const piece of this.pieces) {
      const hovered = zoneKey(piece.userData.zone as Vec3) === this.hovered;
      piece.material.color.set(hovered ? this.theme.bgHover : this.theme.bgRaised);
    }
    this.edges.material.color.set(this.theme.borderStrong);
    this.drawLabels();
  }

  private drawLabels(): void {
    const labels = this.labels;
    if (!labels || typeof document === 'undefined') return;
    // Texture pixels per CSS pixel of the central face area.
    const areaPx = (VIEW_CUBE_PX / (2 * FRUSTUM)) * 2 * (1 - ZONE_BAND);
    const scale = LABEL_TEXTURE_PX / areaPx;
    for (const [face, material] of this.labelMaterials) {
      const canvas = document.createElement('canvas');
      canvas.width = LABEL_TEXTURE_PX;
      canvas.height = LABEL_TEXTURE_PX;
      const context = canvas.getContext('2d');
      if (!context) continue;
      const text = labels[face as keyof CubeLabels];
      let size = LABEL_PX * scale;
      context.font = `600 ${size}px ${this.theme.font}`;
      const width = context.measureText(text).width;
      // Long words shrink to the face instead of overflowing it.
      if (width > LABEL_TEXTURE_PX * 0.92) {
        size *= (LABEL_TEXTURE_PX * 0.92) / width;
        context.font = `600 ${size}px ${this.theme.font}`;
      }
      context.fillStyle = this.theme.text;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(text, LABEL_TEXTURE_PX / 2, LABEL_TEXTURE_PX / 2);
      material.map?.dispose();
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 4;
      material.map = texture;
      material.needsUpdate = true;
    }
  }
}
