import { describe, expect, it } from 'vitest';

import { parseNumberInput } from './numberInput';

const de = (text: string, kind: 'length' | 'angle' | 'count' | 'plain' = 'length') =>
  parseNumberInput(text, { language: 'de', kind });
const en = (text: string, kind: 'length' | 'angle' | 'count' | 'plain' = 'length') =>
  parseNumberInput(text, { language: 'en', kind });

describe('parseNumberInput', () => {
  it('reads German decimals with a comma', () => {
    expect(de('12,5')).toEqual({ ok: true, value: 12.5 });
    expect(de('0,041')).toEqual({ ok: true, value: 0.041 });
  });

  it('accepts an unambiguous point in German lengths', () => {
    expect(de('12.5')).toEqual({ ok: true, value: 12.5 });
  });

  it('rejects a German point that could be a thousands separator', () => {
    expect(de('1.250')).toEqual({ ok: false, reason: 'ambiguous' });
  });

  it('reads German count fields with points as thousands', () => {
    expect(de('200.000', 'count')).toEqual({ ok: true, value: 200_000 });
    expect(de('1,5', 'count')).toEqual({ ok: false, reason: 'invalid' });
  });

  it('reads English numbers with thousands separators', () => {
    expect(en('1,250.5')).toEqual({ ok: true, value: 1250.5 });
    expect(en('200,000', 'count')).toEqual({ ok: true, value: 200_000 });
  });

  it('evaluates simple expressions', () => {
    expect(de('25,4/2')).toEqual({ ok: true, value: 12.7 });
    expect(en('(10 + 2) * 3')).toEqual({ ok: true, value: 36 });
    expect(de('−5 + 2')).toEqual({ ok: true, value: -3 });
  });

  it('converts length units to millimetres', () => {
    expect(en('1 in')).toEqual({ ok: true, value: 25.4 });
    expect(de('2 cm')).toEqual({ ok: true, value: 20 });
    expect(de('0,5"')).toEqual({ ok: true, value: 12.7 });
  });

  it('ignores the degree sign in angle fields', () => {
    expect(de('45°', 'angle')).toEqual({ ok: true, value: 45 });
  });

  it('reports empty and invalid input', () => {
    expect(de('  ')).toEqual({ ok: false, reason: 'empty' });
    expect(de('abc')).toEqual({ ok: false, reason: 'invalid' });
    expect(de('1/0')).toEqual({ ok: false, reason: 'invalid' });
    expect(de('(1 + 2')).toEqual({ ok: false, reason: 'invalid' });
  });
});
