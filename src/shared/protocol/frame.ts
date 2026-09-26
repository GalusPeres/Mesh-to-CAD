// Length-prefixed frames between the application and the kernel. Layout and rules
// are documented in kernel/m2c_kernel/protocol/frame.py; both sides are tested
// against tests/fixtures/frame-vectors.json.

import { MAX_FRAME_BYTES } from './generated/limits';

const MAGIC = [0x4d, 0x32, 0x43, 0x46]; // "M2CF"
const PREFIX_BYTES = 12;
const ALIGNMENT = 8;

export interface Frame {
  header: Record<string, unknown>;
  buffers: Uint8Array[];
}

export class FrameError extends Error {
  override name = 'FrameError';
}

export function padding(length: number): number {
  return (ALIGNMENT - (length % ALIGNMENT)) % ALIGNMENT;
}

/** Encode one frame as a list of chunks; writing them in order produces the frame. */
export function encodeFrame(
  header: Record<string, unknown>,
  buffers: readonly ArrayBufferView[] = [],
): Uint8Array[] {
  const views = buffers.map(
    (buffer) => new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength),
  );
  const headerBytes = new TextEncoder().encode(
    JSON.stringify({ ...header, buffers: views.map((view) => view.byteLength) }),
  );
  const headerPad = padding(PREFIX_BYTES + headerBytes.byteLength);
  const bodyLength = views.reduce(
    (sum, view) => sum + view.byteLength + padding(view.byteLength),
    0,
  );
  const total = PREFIX_BYTES + headerBytes.byteLength + headerPad + bodyLength;
  if (total > MAX_FRAME_BYTES) {
    throw new FrameError(`frame of ${total} bytes exceeds the limit of ${MAX_FRAME_BYTES}`);
  }

  const prefix = new Uint8Array(PREFIX_BYTES + headerBytes.byteLength + headerPad);
  prefix.set(MAGIC, 0);
  const view = new DataView(prefix.buffer);
  view.setUint32(4, headerBytes.byteLength, true);
  view.setUint32(8, bodyLength, true);
  prefix.set(headerBytes, PREFIX_BYTES);

  const chunks: Uint8Array[] = [prefix];
  for (const buffer of views) {
    chunks.push(buffer);
    const pad = padding(buffer.byteLength);
    if (pad) chunks.push(new Uint8Array(pad));
  }
  return chunks;
}

/** Encode one frame into a single contiguous array (tests and small messages). */
export function encodeFrameBytes(
  header: Record<string, unknown>,
  buffers: readonly ArrayBufferView[] = [],
): Uint8Array {
  const chunks = encodeFrame(header, buffers);
  const result = new Uint8Array(chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0));
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

/**
 * Incremental frame parser for a byte stream. Feed it the chunks as they arrive;
 * it returns every frame completed by the chunk. Buffers are views into the
 * received bytes; callers copy them if they must outlive the next chunk.
 */
export class FrameReader {
  private chunks: Uint8Array[] = [];
  private length = 0;

  push(chunk: Uint8Array): Frame[] {
    this.chunks.push(chunk);
    this.length += chunk.byteLength;
    const frames: Frame[] = [];
    for (let frame = this.next(); frame; frame = this.next()) frames.push(frame);
    return frames;
  }

  private next(): Frame | null {
    if (this.length < PREFIX_BYTES) return null;
    const prefix = this.peek(PREFIX_BYTES);
    if (!MAGIC.every((byte, index) => prefix[index] === byte)) {
      throw new FrameError('bad magic at frame start');
    }
    const view = new DataView(prefix.buffer, prefix.byteOffset, PREFIX_BYTES);
    const headerLength = view.getUint32(4, true);
    const bodyLength = view.getUint32(8, true);
    const headerEnd = PREFIX_BYTES + headerLength;
    const total = headerEnd + padding(headerEnd) + bodyLength;
    if (total > MAX_FRAME_BYTES) throw new FrameError('frame exceeds the size limit');
    if (this.length < total) return null;

    const bytes = this.take(total);
    const headerText = new TextDecoder().decode(bytes.subarray(PREFIX_BYTES, headerEnd));
    const header = JSON.parse(headerText) as unknown;
    if (typeof header !== 'object' || header === null || Array.isArray(header)) {
      throw new FrameError('frame header is not a JSON object');
    }
    const record = header as Record<string, unknown>;
    return {
      header: record,
      buffers: splitBuffers(record, bytes.subarray(headerEnd + padding(headerEnd))),
    };
  }

  private peek(count: number): Uint8Array {
    const first = this.chunks[0];
    if (first && first.byteLength >= count) return first.subarray(0, count);
    return this.collect(count, false);
  }

  private take(count: number): Uint8Array {
    const first = this.chunks[0];
    if (first && first.byteLength >= count) {
      const bytes = first.subarray(0, count);
      if (first.byteLength === count) this.chunks.shift();
      else this.chunks[0] = first.subarray(count);
      this.length -= count;
      return bytes;
    }
    return this.collect(count, true);
  }

  private collect(count: number, consume: boolean): Uint8Array {
    const result = new Uint8Array(count);
    let filled = 0;
    let index = 0;
    while (filled < count) {
      const chunk = this.chunks[index];
      if (!chunk) throw new FrameError('not enough data');
      const part = chunk.subarray(0, Math.min(chunk.byteLength, count - filled));
      result.set(part, filled);
      filled += part.byteLength;
      index += 1;
    }
    if (consume) {
      let remaining = count;
      while (remaining > 0) {
        const chunk = this.chunks[0];
        if (!chunk) break;
        if (chunk.byteLength <= remaining) {
          remaining -= chunk.byteLength;
          this.chunks.shift();
        } else {
          this.chunks[0] = chunk.subarray(remaining);
          remaining = 0;
        }
      }
      this.length -= count;
    }
    return result;
  }
}

function splitBuffers(header: Record<string, unknown>, body: Uint8Array): Uint8Array[] {
  const sizes = header.buffers ?? [];
  if (!Array.isArray(sizes) || !sizes.every((size) => Number.isInteger(size) && size >= 0)) {
    throw new FrameError("header field 'buffers' must be a list of sizes");
  }
  const buffers: Uint8Array[] = [];
  let offset = 0;
  for (const size of sizes as number[]) {
    if (offset + size > body.byteLength) throw new FrameError('buffer sizes exceed the frame body');
    buffers.push(body.subarray(offset, offset + size));
    offset += size + padding(size);
  }
  return buffers;
}
