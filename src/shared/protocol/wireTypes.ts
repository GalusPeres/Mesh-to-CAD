// Types used by the generated protocol files in ./generated.

/** Reference to an array stored in the kernel's session (`blob:<sha256>`). */
export type BlobRef = string & { readonly __brand: 'BlobRef' };

export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type Caller = 'renderer' | 'main' | 'test';

/** Metadata of a protocol method, generated from its `@command` decorator. */
export interface MethodInfo {
  readonly lane: boolean;
  readonly caller: Caller;
  readonly exclusive: boolean;
}

export type DType = 'uint8' | 'uint16' | 'uint32' | 'int32' | 'float32' | 'float64';

/** How an array is referenced from the JSON part of a message. */
export interface BufferRef {
  $buf: number;
  dtype: DType;
  shape: number[];
}

export type TypedArray =
  Uint8Array | Uint16Array | Uint32Array | Int32Array | Float32Array | Float64Array;
