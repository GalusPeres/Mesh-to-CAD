import { describe, expect, it } from 'vitest';

import type { FeatureStatus } from '@shared/protocol/generated/document-results';

import { shownStatus } from './featureState';

const status = (codes: string[]): FeatureStatus => ({
  state: codes.length ? 'warning' : 'ok',
  issues: codes.map((code) => ({ code, params: {} })),
  error: null,
  stats: {},
});

const net = { id: 'f2', suppressed: false };

describe('shown feature status', () => {
  it('warns about an open net that stands alone', () => {
    expect(shownStatus(net, status(['surfacing.openNet']), new Set())).toEqual({
      state: 'warning',
      issues: [{ code: 'surfacing.openNet', params: {} }],
    });
  });

  it('drops the open-net warning once a later feature trims the net', () => {
    expect(shownStatus(net, status(['surfacing.openNet']), new Set(['f2']))).toEqual({
      state: 'ok',
      issues: [],
    });
  });

  it('keeps other warnings of a used feature', () => {
    const shown = shownStatus(net, status(['surfacing.openNet', 'fit.poorFit']), new Set(['f2']));
    expect(shown.state).toBe('warning');
    expect(shown.issues.map((issue) => issue.code)).toEqual(['fit.poorFit']);
  });

  it('shows suppressed features as suppressed', () => {
    expect(shownStatus({ id: 'f2', suppressed: true }, undefined, new Set()).state).toBe(
      'suppressed',
    );
  });
});
