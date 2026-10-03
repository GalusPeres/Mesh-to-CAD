import { describe, expect, it } from 'vitest';

import type { SceneItem } from '@shared/protocol/generated/document-display';

import { type ItemVisibility, itemShown } from './itemVisibility';

const item = (style: SceneItem['style'], owner: string, bodyId: string | null = null) =>
  ({ key: `${owner}:${style}`, kind: 'mesh', style, owner, bodyId }) as SceneItem;

const faces = item('body', 'f3', 'f1');
const edges = item('bodyEdges', 'f3', 'f1');
const section = item('section', 'f1');
const plane = item('construction', 'f2', 'f2');
const sketch = item('sketch', 'f4');

const visibility = (change: Partial<ItemVisibility> = {}): ItemVisibility => ({
  bodyEdges: true,
  editedOwner: null,
  hiddenBodies: new Set(),
  hiddenOwners: new Set(),
  ...change,
});

const shown = (v: ItemVisibility) =>
  [faces, edges, section, plane, sketch].filter((i) => itemShown(i, v)).map((i) => i.key);

describe('item visibility', () => {
  it('draws everything by default', () => {
    expect(shown(visibility())).toHaveLength(5);
  });

  it('hides the sections of a used loft but keeps its body, whoever changed it last', () => {
    expect(shown(visibility({ hiddenOwners: new Set(['f1']) }))).toEqual([
      faces.key,
      edges.key,
      plane.key,
      sketch.key,
    ]);
  });

  it('hides a body by its id, not by the feature that changed it last', () => {
    expect(shown(visibility({ hiddenOwners: new Set(['f3']) }))).toHaveLength(5);
    expect(shown(visibility({ hiddenBodies: new Set(['f1']) }))).toEqual([
      section.key,
      plane.key,
      sketch.key,
    ]);
  });

  it('hides construction with a body id by its owner', () => {
    expect(shown(visibility({ hiddenBodies: new Set(['f2']) }))).toContain(plane.key);
    expect(shown(visibility({ hiddenOwners: new Set(['f2', 'f4']) }))).toEqual([
      faces.key,
      edges.key,
      section.key,
    ]);
  });

  it('leaves out body edges in shaded mode and the feature a tool edits', () => {
    expect(shown(visibility({ bodyEdges: false }))).not.toContain(edges.key);
    expect(shown(visibility({ editedOwner: 'f4' }))).not.toContain(sketch.key);
  });
});
