// Moves typed arrays between message values and separate binary buffers.
// Arrays are sent flat (row-major); the kernel reshapes them where it needs to.

import type { BufferRef, DType, TypedArray } from './wireTypes';

const CONSTRUCTORS = {
  uint8: Uint8Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
  int32: Int32Array,
  float32: Float32Array,
  float64: Float64Array,
} as const;

function dtypeOf(array: TypedArray): DType {
  if (array instanceof Uint8Array) return 'uint8';
  if (array instanceof Uint16Array) return 'uint16';
  if (array instanceof Uint32Array) return 'uint32';
  if (array instanceof Int32Array) return 'int32';
  if (array instanceof Float32Array) return 'float32';
  return 'float64';
}

function isTypedArray(value: unknown): value is TypedArray {
  return ArrayBuffer.isView(value) && !(value instanceof DataView) && dtypeOfSupported(value);
}

function dtypeOfSupported(value: ArrayBufferView): boolean {
  return Object.values(CONSTRUCTORS).some((constructor) => value instanceof constructor);
}

function isBufferRef(value: unknown): value is BufferRef {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { $buf?: unknown }).$buf === 'number' &&
    typeof (value as { dtype?: unknown }).dtype === 'string'
  );
}

export interface EncodedMessage {
  json: unknown;
  buffers: ArrayBuffer[];
}

/** Replace every typed array in `value` with a buffer reference and collect the bytes. */
export function encodeBuffers(value: unknown): EncodedMessage {
  const buffers: ArrayBuffer[] = [];
  const walk = (item: unknown): unknown => {
    if (isTypedArray(item)) {
      const bytes = item.buffer.slice(item.byteOffset, item.byteOffset + item.byteLength);
      buffers.push(bytes as ArrayBuffer);
      const ref: BufferRef = {
        $buf: buffers.length - 1,
        dtype: dtypeOf(item),
        shape: [item.length],
      };
      return ref;
    }
    if (Array.isArray(item)) return item.map(walk);
    if (typeof item === 'object' && item !== null) {
      return Object.fromEntries(Object.entries(item).map(([key, entry]) => [key, walk(entry)]));
    }
    return item;
  };
  return { json: walk(value), buffers };
}

/** Replace buffer references with typed arrays viewing the received buffers (no copies). */
export function decodeBuffers(value: unknown, buffers: readonly ArrayBuffer[]): unknown {
  const walk = (item: unknown): unknown => {
    if (isBufferRef(item)) {
      const buffer = buffers[item.$buf];
      if (!buffer) throw new Error(`message references missing buffer ${item.$buf}`);
      return new CONSTRUCTORS[item.dtype](buffer);
    }
    if (Array.isArray(item)) return item.map(walk);
    if (typeof item === 'object' && item !== null) {
      return Object.fromEntries(Object.entries(item).map(([key, entry]) => [key, walk(entry)]));
    }
    return item;
  };
  return walk(value);
}
