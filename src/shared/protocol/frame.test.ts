import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { FrameError, FrameReader, encodeFrameBytes } from './frame';

interface Vector {
  name: string;
  header: Record<string, unknown>;
  buffers: string[];
  frame: string;
}

const VECTORS = JSON.parse(
  readFileSync(
    path.resolve(import.meta.dirname, '../../../tests/fixtures/frame-vectors.json'),
    'utf8',
  ),
) as Vector[];

const fromHex = (hex: string) => Uint8Array.from(Buffer.from(hex, 'hex'));
const toHex = (bytes: Uint8Array) => Buffer.from(bytes).toString('hex');

describe('frames', () => {
  it.each(VECTORS)('encodes like the kernel: $name', (vector) => {
    expect(toHex(encodeFrameBytes(vector.header, vector.buffers.map(fromHex)))).toBe(vector.frame);
  });

  it.each(VECTORS)('decodes the kernel encoding: $name', (vector) => {
    const [frame] = new FrameReader().push(fromHex(vector.frame));
    expect(frame?.header).toMatchObject(vector.header);
    expect(frame?.buffers.map(toHex)).toEqual(vector.buffers);
  });

  it('reassembles frames split across chunks and returns several frames from one chunk', () => {
    const bytes = VECTORS.map((vector) => fromHex(vector.frame));
    const stream = Buffer.concat(bytes);
    const reader = new FrameReader();
    const frames = [];
    for (let offset = 0; offset < stream.length; offset += 7) {
      frames.push(...reader.push(Uint8Array.from(stream.subarray(offset, offset + 7))));
    }
    expect(frames).toHaveLength(VECTORS.length);
    expect(new FrameReader().push(Uint8Array.from(stream))).toHaveLength(VECTORS.length);
  });

  it('rejects a stream that does not start with the magic', () => {
    expect(() => new FrameReader().push(new Uint8Array(16))).toThrow(FrameError);
  });
});
