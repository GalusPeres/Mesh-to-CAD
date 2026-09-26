import { describe, expect, it } from 'vitest';

import { createFormatter } from './format';

describe('createFormatter', () => {
  const de = createFormatter('de-DE');
  const en = createFormatter('en-US');

  it('formats lengths with three decimals and the unit', () => {
    expect(de.length(0.041)).toBe('0,041 mm');
    expect(en.length(0.041)).toBe('0.041 mm');
  });

  it('formats counts with grouping', () => {
    expect(de.count(1_204_566)).toBe('1.204.566');
    expect(en.count(1_204_566)).toBe('1,204,566');
  });

  it('always shows the sign of signed lengths', () => {
    expect(de.length(0.1, { signed: true })).toBe('+0,100 mm');
    expect(de.length(-0.1, { signed: true })).toBe('−0,100 mm');
  });

  it('never shows a negative zero', () => {
    expect(en.length(-0.0001)).toBe('0.000 mm');
  });

  it('formats angles and percentages', () => {
    expect(de.angle(45)).toBe('45,00°');
    expect(de.percent(0.987)).toBe('98,7 %');
  });

  it('joins lists in the language', () => {
    expect(de.list(['Extrusion 1', 'Verrundung 1'])).toBe('Extrusion 1 und Verrundung 1');
    expect(en.list(['a', 'b', 'c'])).toBe('a, b, and c');
  });
});
