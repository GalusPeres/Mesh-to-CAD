/** Join class names, skipping empty values. */
export function classNames(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(' ');
}
