import { appendFileSync, existsSync, mkdirSync, renameSync, rmSync, statSync } from 'node:fs';
import path from 'node:path';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface Logger {
  debug(message: string): void;
  info(message: string): void;
  warn(message: string): void;
  error(message: string, error?: unknown): void;
}

const MAX_BYTES = 5 * 1024 * 1024;
const KEEP_FILES = 5;

/**
 * Appends lines to a log file and rotates it at 5 MB, keeping five old files
 * (`main.log`, `main.1.log`, ...). Writes are synchronous: log volume is small
 * and a crash must not lose the last lines.
 */
export class FileLogger implements Logger {
  private readonly file: string;

  constructor(
    directory: string,
    private readonly name: string,
    private readonly mirror: ((line: string) => void) | null = null,
  ) {
    mkdirSync(directory, { recursive: true });
    this.file = path.join(directory, `${name}.log`);
    this.rotateIfLarge();
  }

  debug(message: string): void {
    this.write('debug', message);
  }

  info(message: string): void {
    this.write('info', message);
  }

  warn(message: string): void {
    this.write('warn', message);
  }

  error(message: string, error?: unknown): void {
    const detail = error instanceof Error ? `\n${error.stack ?? error.message}` : '';
    this.write('error', message + detail);
  }

  /** A line that already carries its own timestamp and level (kernel stderr). */
  raw(line: string): void {
    this.append(line);
  }

  private write(level: LogLevel, message: string): void {
    this.append(`${new Date().toISOString()} ${level.toUpperCase()} ${this.name}: ${message}`);
  }

  private append(line: string): void {
    try {
      appendFileSync(this.file, line + '\n', 'utf8');
    } catch {
      // Logging must never take the application down.
    }
    this.mirror?.(line);
  }

  private rotateIfLarge(): void {
    if (!existsSync(this.file) || statSync(this.file).size < MAX_BYTES) return;
    const numbered = (index: number) =>
      path.join(path.dirname(this.file), `${this.name}.${index}.log`);
    rmSync(numbered(KEEP_FILES - 1), { force: true });
    for (let index = KEEP_FILES - 2; index >= 1; index -= 1) {
      if (existsSync(numbered(index))) renameSync(numbered(index), numbered(index + 1));
    }
    renameSync(this.file, numbered(1));
  }
}
