// Step: a new project with the remote scan, reduced to 1 M triangles, aligned
// automatically and turned over (flip Z) so the buttons face up.

import { applyOps, shown } from '../scene.mjs';

const WORKING_FACES = 1_000_000;

export const importScan = {
  id: 'import',
  title: 'Import, reduce to 1 M, auto alignment with flip Z',
  async run(ctx) {
    const { d } = ctx;
    await d.kernel('project.new');
    await shown(d);
    const pending = await d.kernel('mesh.import', { path: ctx.scanPath });
    await d.kernel('mesh.commitImport', {
      pendingId: pending.pendingId,
      unit: 'mm',
      reduceTo: pending.faceCount > WORKING_FACES ? WORKING_FACES : null,
    });
    await applyOps(
      d,
      [
        {
          type: 'setAlignment',
          method: 'auto',
          params: null,
          adjust: { flipZ: true, flipX: false, rotateZ90: 0 },
        },
      ],
      'alignment',
    );
    const bounds = await d.kernel('automation.bounds');
    ctx.bounds = bounds;
    return {
      trianglesInFile: pending.faceCount,
      triangles: bounds.faces,
      size: bounds.max.map((value, axis) => +(value - bounds.min[axis]).toFixed(2)),
    };
  },
};
