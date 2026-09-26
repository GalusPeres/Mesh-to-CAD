// Parsing of numeric fields (docs/DESIGN.md 4, NumberField).
//
// Accepted: simple expressions (`25,4/2`, `(10 + 2) * 3`) and, in length fields,
// a unit suffix (`1 in`, `12 cm`). Decimal separators follow the language, with
// one safety rule: in German a point followed by exactly three digits (`1.250`)
// could be a thousands separator, so length and angle fields reject it and ask
// for a comma, while count fields read it as thousands (`200.000` = 200 000).

export type NumberKind = 'length' | 'angle' | 'count' | 'plain';

export type ParseResult =
  { ok: true; value: number } | { ok: false; reason: 'empty' | 'invalid' | 'ambiguous' };

const UNIT_FACTORS: Record<string, number> = { mm: 1, cm: 10, m: 1000, in: 25.4, '"': 25.4 };

class InvalidInput extends Error {
  constructor(readonly reason: 'invalid' | 'ambiguous') {
    super(reason);
  }
}

function normaliseLiteral(literal: string, language: 'de' | 'en', kind: NumberKind): string {
  const decimal = language === 'de' ? ',' : '.';
  const grouping = language === 'de' ? '.' : ',';
  const groupedThousands = new RegExp(`\\${grouping}\\d{3}(?!\\d)`);

  if (kind === 'count') {
    const digits = literal.split(grouping).join('');
    if (!/^\d+$/.test(digits)) throw new InvalidInput('invalid');
    return digits;
  }
  if (literal.includes(grouping) && literal.includes(decimal)) {
    // Both separators: valid only as grouped thousands followed by decimals (1.250,5).
    const [integer = '', fraction = '', ...rest] = literal.split(decimal);
    const grouped = new RegExp(`^\\d{1,3}(\\${grouping}\\d{3})+$`);
    if (rest.length || !grouped.test(integer) || !/^\d+$/.test(fraction)) {
      throw new InvalidInput('invalid');
    }
    return `${integer.split(grouping).join('')}.${fraction}`;
  }
  if (literal.includes(grouping)) {
    if (groupedThousands.test(literal)) {
      if (language === 'de') throw new InvalidInput('ambiguous');
      return literal.split(grouping).join('');
    }
    return literal.replace(grouping, '.');
  }
  return literal.replace(decimal, '.');
}

class ExpressionParser {
  private position = 0;

  constructor(private readonly tokens: string[]) {}

  parse(): number {
    const value = this.sum();
    if (this.position !== this.tokens.length) throw new InvalidInput('invalid');
    return value;
  }

  private sum(): number {
    let value = this.product();
    for (let token = this.peek(); token === '+' || token === '-'; token = this.peek()) {
      this.position += 1;
      value = token === '+' ? value + this.product() : value - this.product();
    }
    return value;
  }

  private product(): number {
    let value = this.unary();
    for (let token = this.peek(); token === '*' || token === '/'; token = this.peek()) {
      this.position += 1;
      value = token === '*' ? value * this.unary() : value / this.unary();
    }
    return value;
  }

  private unary(): number {
    const token = this.peek();
    if (token === '-' || token === '+') {
      this.position += 1;
      return token === '-' ? -this.unary() : this.unary();
    }
    if (token === '(') {
      this.position += 1;
      const value = this.sum();
      if (this.peek() !== ')') throw new InvalidInput('invalid');
      this.position += 1;
      return value;
    }
    if (token === undefined || !/^[\d.]+$/.test(token)) throw new InvalidInput('invalid');
    this.position += 1;
    return Number(token);
  }

  private peek(): string | undefined {
    return this.tokens[this.position];
  }
}

/** Parse a field value; lengths are returned in millimetres. */
export function parseNumberInput(
  text: string,
  options: { language: 'de' | 'en'; kind: NumberKind },
): ParseResult {
  let input = text.trim().replace(/−/g, '-');
  if (!input) return { ok: false, reason: 'empty' };

  let factor = 1;
  if (options.kind === 'length') {
    const unit = /\s*(mm|cm|m|in|")$/i.exec(input);
    if (unit) {
      factor = UNIT_FACTORS[(unit[1] ?? '').toLowerCase()] ?? 1;
      input = input.slice(0, unit.index);
    }
  } else if (options.kind === 'angle') {
    input = input.replace(/\s*(°|deg)$/i, '');
  }

  try {
    const tokens = input.match(/\d[\d.,]*|[+\-*/()]|\S/g) ?? [];
    const normalised = tokens.map((token) =>
      /^\d/.test(token) ? normaliseLiteral(token, options.language, options.kind) : token,
    );
    const value = new ExpressionParser(normalised).parse() * factor;
    if (!Number.isFinite(value)) return { ok: false, reason: 'invalid' };
    if (options.kind === 'count' && !Number.isInteger(value))
      return { ok: false, reason: 'invalid' };
    return { ok: true, value };
  } catch (error) {
    if (error instanceof InvalidInput) return { ok: false, reason: error.reason };
    throw error;
  }
}
