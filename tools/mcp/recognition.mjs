// MCP tools of shape recognition (Formen erkennen): read the scan like a designer and
// build the chosen shapes as editable features (docs/AUTOMATION.md).

import { z } from 'zod';

/**
 * Register `recognize_shapes` and `build_shapes` with the server's helpers: `tool`
 * registers a tool, `kernel` calls a kernel method, `text` wraps a result and
 * `summarise` condenses a document snapshot.
 */
export function registerRecognitionTools({ tool, kernel, text, summarise }) {
  const round = (value) => Math.round(value * 1000) / 1000;

  /** The recognition without its outline buffers, values rounded to micrometres. */
  function describeRecognition(result) {
    return {
      planes: result.planes.map((plane, index) => ({
        index,
        origin: plane.origin.map(round),
        normal: plane.normal.map(round),
        areaMm2: Math.round(plane.area),
      })),
      features: result.features.map((feature, index) => ({
        index,
        plane: feature.plane,
        role: feature.kind === 'boss' ? 'raised' : feature.top === 'through' ? 'hole' : 'pocket',
        shape: feature.shape,
        params: Object.fromEntries(
          Object.entries(feature.params).map(([name, value]) => [name, round(value)]),
        ),
        levelMm: round(feature.level),
        heightMm: round(feature.height),
        top: feature.top,
        inPocket: feature.parent,
        group: feature.group,
        labelAt: feature.label.map(round),
      })),
    };
  }

  tool(
    'recognize_shapes',
    {
      description:
        'Read the aligned scan like a designer (like Formen erkennen): its flat faces and, on ' +
        'them, raised shapes, pockets and holes. Every outline is lines and arcs, named circle, ' +
        'cutCircle (a circle trimmed by the part outline: radius, cut normal angle, cut distance ' +
        'from the centre), slot, roundedRect or ringSegment where one fits, else "profile" (a ' +
        'free outline: centre and extent). Design intent applied (equal sizes, shared centres, ' +
        'rounded values). Outline params are in the plane frame (mm, radians). Follow with ' +
        'build_shapes.',
    },
    async () => {
      const { document } = await kernel('doc.get');
      if (!document.scan) throw new Error('No scan loaded.');
      const result = await kernel(
        'recognize.run',
        { scanKey: document.scan.key },
        'recognize.run:mcp',
      );
      return text(describeRecognition(result));
    },
  );

  tool(
    'build_shapes',
    {
      description:
        'Build recognised shapes of the last recognize_shapes as editable features: a fitted ' +
        'plane, one sketch per level and one extrusion per group, as one undoable step. Raised ' +
        'shapes join targetBody (or become new bodies without one); pockets and holes are cut ' +
        'from targetBody and need one.',
      inputSchema: {
        features: z
          .array(z.number().int().min(0))
          .optional()
          .describe('Feature indices from recognize_shapes; default: all of them'),
        targetBody: z.string().nullable().optional().describe('Body id, e.g. "f2"'),
      },
    },
    async ({ features, targetBody }) => {
      const { revision, document } = await kernel('doc.get');
      if (!document.scan) throw new Error('No scan loaded.');
      let chosen = features;
      if (!chosen) {
        const found = await kernel(
          'recognize.run',
          { scanKey: document.scan.key },
          'recognize.run:mcp',
        );
        chosen = found.features.map((_, index) => index);
      }
      const built = await kernel('recognize.build', {
        scanKey: document.scan.key,
        baseRevision: revision,
        features: chosen,
        targetBody: targetBody ?? null,
      });
      return text({ ...built, document: summarise(await kernel('doc.get')) });
    },
  );
}
