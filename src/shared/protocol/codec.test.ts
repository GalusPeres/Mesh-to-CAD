import { describe, expect, it } from 'vitest';

import { decodeBuffers, encodeBuffers } from './codec';

describe('buffer codec', () => {
  it('moves typed arrays out of a message and back', () => {
    const faces = new Uint32Array([4, 8, 15]);
    const { json, buffers } = encodeBuffers({
      faces,
      nested: [{ values: new Float32Array([0.5]) }],
      label: 'x',
    });
    expect(json).toEqual({
      faces: { $buf: 0, dtype: 'uint32', shape: [3] },
      nested: [{ values: { $buf: 1, dtype: 'float32', shape: [1] } }],
      label: 'x',
    });
    const decoded = decodeBuffers(json, buffers) as {
      faces: Uint32Array;
      nested: [{ values: Float32Array }];
    };
    expect(Array.from(decoded.faces)).toEqual([4, 8, 15]);
    expect(decoded.nested[0].values).toBeInstanceOf(Float32Array);
  });

  it('copies only the viewed part of a larger buffer', () => {
    const backing = new Uint16Array([1, 2, 3, 4]);
    const { buffers } = encodeBuffers({ part: backing.subarray(1, 3) });
    expect(Array.from(new Uint16Array(buffers[0]!))).toEqual([2, 3]);
  });

  it('fails on a reference to a missing buffer', () => {
    expect(() => decodeBuffers({ $buf: 2, dtype: 'uint8', shape: [1] }, [])).toThrow();
  });
});
