// The only place that formats numbers for display (docs/DESIGN.md 8.2).
// Lengths have three decimals, angles two, percentages one; units are always shown.

export interface Formatter {
  readonly locale: string;
  number(value: number, decimals: number): string;
  count(value: number): string;
  length(millimetres: number, options?: { signed?: boolean; decimals?: number }): string;
  angle(degrees: number): string;
  percent(fraction: number): string;
  area(squareMillimetres: number): string;
  volume(cubicMillimetres: number): string;
  bytes(bytes: number): string;
  list(items: readonly string[]): string;
}

const MINUS = '−';

export function createFormatter(locale: string): Formatter {
  const fixed = new Map<number, Intl.NumberFormat>();
  const numberFormat = (decimals: number) => {
    let format = fixed.get(decimals);
    if (!format) {
      format = new Intl.NumberFormat(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
      fixed.set(decimals, format);
    }
    return format;
  };
  const counts = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const lists = new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' });

  const signed = (value: number, decimals: number, always: boolean) => {
    const text = numberFormat(decimals).format(Math.abs(value));
    if (value < 0 && Number(text.replace(/\D/g, '')) !== 0) return `${MINUS}${text}`;
    return always ? `+${text}` : text;
  };

  return {
    locale,
    number: (value, decimals) => signed(value, decimals, false),
    count: (value) => counts.format(value),
    length: (value, options = {}) =>
      `${signed(value, options.decimals ?? 3, options.signed ?? false)} mm`,
    angle: (value) => `${signed(value, 2, false)}°`,
    percent: (fraction) => `${numberFormat(1).format(fraction * 100)} %`,
    area: (value) => `${numberFormat(1).format(value)} mm²`,
    volume: (value) => `${numberFormat(1).format(value)} mm³`,
    bytes: (value) => {
      if (value < 1024) return `${counts.format(value)} B`;
      if (value < 1024 * 1024) return `${numberFormat(0).format(value / 1024)} KB`;
      return `${numberFormat(1).format(value / (1024 * 1024))} MB`;
    },
    list: (items) => lists.format(items),
  };
}
