// Face ids in the face-id render target: face index + 1 in the four bytes of an
// RGBA8 pixel, least significant byte in red, 0 where no face is drawn. Read back
// as a Uint32Array on the same bytes, a pixel is the id directly (little endian).

/** A read-back face-id image. Rows run bottom to top, as WebGL returns them. */
export interface FaceIdImage {
  ids: Uint32Array;
  /** Size in image pixels. */
  width: number;
  height: number;
  /** Image pixels per CSS pixel. */
  scale: number;
}

/** The bytes the id shader writes for a face (mirrors the GLSL in faceIdPass.ts). */
export function encodeFaceId(face: number): [number, number, number, number] {
  const id = face + 1;
  return [id & 255, (id >>> 8) & 255, (id >>> 16) & 255, (id >>> 24) & 255];
}

export function decodeFaceId(r: number, g: number, b: number, a: number): number {
  return ((r | (g << 8) | (b << 16) | (a << 24)) >>> 0) - 1;
}

/** Face drawn at a CSS pixel position, or -1 for background and positions outside. */
export function faceIdAt(image: FaceIdImage, x: number, y: number): number {
  const column = Math.floor(x * image.scale);
  const row = image.height - 1 - Math.floor(y * image.scale);
  if (column < 0 || row < 0 || column >= image.width || row >= image.height) return -1;
  return (image.ids[row * image.width + column] ?? 0) - 1;
}
