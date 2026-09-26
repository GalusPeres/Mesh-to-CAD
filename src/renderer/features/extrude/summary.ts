import type { TFunction } from 'i18next';

import type { BodyOperation } from '@shared/protocol/generated/features-common';

/** "12,000 mm, Abziehen": the operation is named unless the feature makes a new body. */
export function withOperation(text: string, operation: BodyOperation, t: TFunction): string {
  if (operation === 'newBody') return text;
  return `${text}, ${t(`tools:extrude.solid.operations.${operation}`)}`;
}
