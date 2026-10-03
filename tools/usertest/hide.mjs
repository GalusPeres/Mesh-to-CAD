// User test of hiding used construction (#25): once Formen erkennen builds on the loft,
// the loft's sections and the used plane and sketch are no longer drawn or picked; the
// eye in the tree shows them again, and undoing the use brings them back.

import { PART } from './part.mjs';

const [LENGTH, WIDTH, HEIGHT] = PART.plate;

async function features(d) {
  return (await d.kernel('doc.get')).document.features;
}

/** What the pointer finds at part points: scan, body, or the owner of an item, each once. */
async function found(d, points) {
  const owners = new Set();
  for (const point of points) {
    const hit = await d.pick(await d.at(point));
    owners.add(hit?.kind === 'item' ? hit.owner : (hit?.kind ?? 'nothing'));
  }
  return [...owners].join(', ');
}

/** Check the picks, giving the view a few seconds to load what the document changed. */
async function expectPick(d, name, points, ok) {
  const last = await d
    .until(
      async () => {
        const what = await found(d, points);
        return ok(what) ? what : null;
      },
      name,
      5_000,
    )
    .catch(() => found(d, points));
  d.check(name, ok(last), last);
}

const is = (id) => (what) => what.split(', ').includes(id);
const not = (id) => (what) => !is(id)(what);

export async function hideTest(d) {
  await d.press('stage-model');
  await d.command('view.front');
  await d.command('view.fitAll');
  await d.press('tool-loft');
  await d.until(
    async () => {
      await d.press('panel-ok').catch(() => undefined);
      return (await features(d)).find((feature) => feature.type === 'loft');
    },
    'the loft',
    60_000,
  );
  await d.settle();
  const loft = (await features(d)).find((feature) => feature.type === 'loft');
  // Up the front wall, away from the boss: the sections lie between these points.
  const wall = Array.from({ length: 17 }, (_, i) => [LENGTH * 0.7, 0, (HEIGHT * (i + 2)) / 20]);
  await expectPick(d, 'the loft sections can be picked on the wall', wall, is(loft.id));

  await d.press('tool-recognize');
  await d.until(async () => {
    const info = await d.toolInfo();
    return !info?.state?.job && info?.groups?.length;
  }, 'the recognised shapes');
  const before = (await features(d)).length;
  await d.press('panel-ok');
  await d.until(async () => (await features(d)).length > before, 'the built shapes');
  await d.settle();
  const plane = (await features(d)).slice(before).find((feature) => feature.type === 'fit');
  await d.command('view.front');
  await d.command('view.fitAll');
  await expectPick(d, 'the used loft sections are not picked', wall, not(loft.id));
  await d.command('view.iso');
  await d.command('view.fitAll');
  const top = [[LENGTH * 0.7, WIDTH / 2, HEIGHT]];
  await expectPick(d, 'the used plane is not picked', top, not(plane.id));
  await d.shot('hide-1-used');

  await d.press(`tree-eye-${plane.id}`);
  await expectPick(d, 'the eye shows the plane again', top, is(plane.id));
  await d.shot('hide-2-eye-shown');
  await d.press(`tree-eye-${plane.id}`);
  await expectPick(d, 'the eye hides it again', top, not(plane.id));

  await d.command('edit.undo');
  await d.until(async () => (await features(d)).length === before, 'the undo');
  await d.settle();
  await d.command('view.front');
  await d.command('view.fitAll');
  await expectPick(d, 'undoing the use brings the sections back', wall, is(loft.id));
  await d.shot('hide-3-undone');
}
