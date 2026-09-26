#!/usr/bin/env node
// MCP server for Mesh-to-CAD (docs/AUTOMATION.md).
//
// It drives the running application through its local automation interface, so
// every change appears live in the user's window and stays undoable there. The
// application publishes port and token in automation.json in its user data
// folder once "Allow control by AI assistants (MCP)" is enabled in the settings
// (or it was started with M2C_AUTOMATION=1).
//
// Coordinates are part coordinates in millimetres (after the alignment), the
// same as the application shows.

import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const PRODUCT = 'Mesh-to-CAD';

function infoPath() {
  if (process.env.M2C_AUTOMATION_INFO) return process.env.M2C_AUTOMATION_INFO;
  const appData = process.env.APPDATA ?? path.join(os.homedir(), 'AppData', 'Roaming');
  return path.join(appData, PRODUCT, 'automation.json');
}

function connection() {
  try {
    return JSON.parse(readFileSync(infoPath(), 'utf8'));
  } catch {
    throw new Error(
      `${PRODUCT} is not reachable. Start the app and enable "Steuerung durch KI-Assistenten ` +
        `erlauben (MCP)" in Datei > Einstellungen (${infoPath()} is missing).`,
    );
  }
}

/** One request to the application's automation interface. */
async function rpc(method, params = {}) {
  const { port, token } = connection();
  const response = await fetch(`http://127.0.0.1:${port}/rpc`, {
    method: 'POST',
    headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify({ method, params }),
  });
  const body = await response.json();
  if (!body.ok) throw new Error(body.error ?? `request failed (${response.status})`);
  return body.result;
}

/** A kernel method; kernel errors become exceptions with their code and parameters. */
async function kernel(method, params = {}, lane) {
  const answer = await rpc('kernel.call', { method, params, lane });
  if (!answer.ok) throw new Error(`${method}: ${JSON.stringify(answer.error)}`);
  return answer.result;
}

const ui = (action) => rpc('ui', { action });
const uint32 = (values) => ({ $typed: 'uint32', values });

async function applyOps(ops, label) {
  const { revision } = await kernel('doc.get');
  return kernel('doc.apply', { baseRevision: revision, ops, label });
}

function summarise(snapshot) {
  const { document, status } = snapshot;
  const scan = document.scan;
  return {
    revision: snapshot.revision,
    scan: scan && {
      file: scan.source?.fileName ?? null,
      faces: scan.faceCount,
      noiseMm: scan.noise,
    },
    alignment: document.alignment?.method ?? null,
    toleranceMm: document.settings?.tolerance,
    features: document.features.map((feature) => {
      const state = status.features[feature.id];
      return {
        id: feature.id,
        type: feature.type,
        name: feature.name,
        state: state?.state,
        issues: state?.issues?.map((issue) => issue.code),
        error: state?.error?.code,
        stats: state?.stats,
      };
    }),
    bodies: status.bodies.map((body) => ({
      id: body.id,
      owner: body.owner,
      valid: body.valid,
      volumeMm3: body.volume,
      areaMm2: body.area,
    })),
  };
}

async function facesInBox({ min, max, facing, maxAngleDeg }) {
  const result = await kernel('automation.facesInBox', {
    min,
    max,
    facing: facing ?? null,
    maxAngleDeg: maxAngleDeg ?? 30,
  });
  return result.faces;
}

const text = (value) => ({
  content: [
    { type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) },
  ],
});

const vec3 = z.tuple([z.number(), z.number(), z.number()]);
const region = {
  min: vec3.describe('Corner of the box in part coordinates (mm)'),
  max: vec3.describe('Opposite corner of the box (mm)'),
  facing: vec3
    .optional()
    .describe('Keep only triangles facing this direction, e.g. [0,0,1] for a top surface'),
  maxAngleDeg: z
    .number()
    .min(0)
    .max(180)
    .optional()
    .describe('Allowed angle to `facing` (default 30)'),
};

const server = new McpServer({ name: 'mesh-to-cad', version: '0.1.0' });

server.registerTool(
  'app_status',
  {
    description:
      'State of the running Mesh-to-CAD app: scan, alignment, feature history with status and ' +
      'statistics, bodies, open tool and selection. Start here.',
  },
  async () => {
    const [ping, snapshot, uiState] = await Promise.all([
      rpc('ping'),
      kernel('doc.get'),
      ui({ type: 'state' }),
    ]);
    return text({ app: ping, ui: uiState, document: summarise(snapshot) });
  },
);

server.registerTool(
  'import_scan',
  {
    description: 'Load a scan (STL, OBJ, PLY) from a file path. Replaces the current scan.',
    inputSchema: {
      path: z.string().describe('Absolute path of the mesh file'),
      unit: z.enum(['mm', 'cm', 'm', 'in']).default('mm'),
      reduceTo: z
        .number()
        .int()
        .positive()
        .optional()
        .describe('Triangle count to reduce to (max 2,000,000)'),
    },
  },
  async ({ path: file, unit, reduceTo }) => {
    const report = await kernel('mesh.import', { path: file });
    const target = reduceTo ?? (report.reductionRequired ? 1_000_000 : null);
    const committed = await kernel('mesh.commitImport', {
      pendingId: report.pendingId,
      unit,
      reduceTo: target,
    });
    return text({
      file: report.fileName,
      trianglesInFile: report.faceCount,
      reducedTo: target,
      boundsInFileUnits: [report.boundsMin, report.boundsMax],
      revision: committed.revision,
    });
  },
);

server.registerTool(
  'align_auto',
  {
    description:
      'Align the scan automatically: largest plane to XY, a perpendicular plane to X. Use the ' +
      'adjustments to turn the part the right way up or around.',
    inputSchema: {
      flipZ: z.boolean().default(false).describe('Turn the part upside down'),
      flipX: z.boolean().default(false),
      rotateZ90: z.number().int().min(0).max(3).default(0).describe('Quarter turns around Z'),
    },
  },
  async ({ flipZ, flipX, rotateZ90 }) => {
    await applyOps(
      [{ type: 'setAlignment', method: 'auto', params: null, adjust: { flipZ, flipX, rotateZ90 } }],
      'alignment',
    );
    return text(await kernel('automation.bounds'));
  },
);

server.registerTool(
  'scan_bounds',
  { description: 'Bounding box of the aligned scan in part coordinates (mm), to choose regions.' },
  async () => text(await kernel('automation.bounds')),
);

server.registerTool(
  'select_region',
  {
    description:
      'Select the scan triangles whose centres lie in a box (optionally only those facing a ' +
      'direction) and show the selection in the app.',
    inputSchema: region,
  },
  async (input) => {
    const faces = await facesInBox(input);
    await ui({ type: 'selectFaces', faces });
    return text({ selectedTriangles: faces.length });
  },
);

server.registerTool(
  'fit_shape',
  {
    description:
      'Fit a plane, cylinder, cone, sphere or torus to the triangles in a box and add it to the ' +
      'history (like Form einpassen). kind "auto" picks the type.',
    inputSchema: {
      ...region,
      kind: z.enum(['auto', 'plane', 'cylinder', 'cone', 'sphere', 'torus']).default('auto'),
      robust: z.boolean().default(false).describe('Ignore other surfaces inside the box'),
    },
  },
  async ({ kind, robust, ...box }) => {
    const faces = await facesInBox(box);
    if (faces.length === 0) throw new Error('No triangles in this box. Check scan_bounds.');
    const scan = (await kernel('doc.get')).document.scan;
    const preview = await kernel(
      'fit.preview',
      { faces: uint32(faces), scanKey: scan.key, kind, robust },
      'fit.preview:mcp',
    );
    const chosen = preview.primitive.type;
    await applyOps(
      [
        {
          type: 'addFeature',
          feature: { type: 'fit', params: { faces: uint32(faces), kind: chosen, robust } },
        },
      ],
      'fit',
    );
    return text({
      kind: chosen,
      triangles: faces.length,
      primitive: preview.primitive,
      stats: preview.stats,
    });
  },
);

server.registerTool(
  'auto_surface',
  {
    description:
      'Turn the whole scan into a smooth solid of B-spline surfaces (Auto-Flächen). Takes seconds ' +
      'to a few minutes. Returns patch count and deviation from the scan.',
    inputSchema: {
      detail: z.enum(['coarse', 'medium', 'fine']).default('medium'),
      smoothing: z.enum(['low', 'medium', 'high']).default('low'),
    },
  },
  async ({ detail, smoothing }) => {
    await applyOps(
      [{ type: 'addFeature', feature: { type: 'autoSurface', params: { detail, smoothing } } }],
      'autoSurface',
    );
    const summary = summarise(await kernel('doc.get'));
    return text({ feature: summary.features.at(-1), bodies: summary.bodies });
  },
);

server.registerTool(
  'export_step',
  {
    description: 'Export bodies as a STEP file (all bodies unless ids are given).',
    inputSchema: {
      path: z.string().describe('Absolute path of the .step file to write'),
      bodies: z.array(z.string()).optional(),
      schema: z.enum(['AP214', 'AP242']).default('AP214'),
    },
  },
  async ({ path: file, bodies, schema }) => {
    const snapshot = await kernel('doc.get');
    const ids = bodies ?? snapshot.status.bodies.map((body) => body.id);
    if (ids.length === 0) throw new Error('There is no body to export yet.');
    return text(await kernel('export.step', { path: file, bodies: ids, names: ids, schema }));
  },
);

server.registerTool(
  'apply_ops',
  {
    description:
      'Apply document operations (addFeature, updateFeature, deleteFeature, setSuppressed, ' +
      'setAlignment, setSettings) as one undoable step. Params use the wire format of ' +
      'src/shared/protocol/generated; typed arrays as {"$typed":"uint32","values":[...]}.',
    inputSchema: {
      ops: z.array(z.record(z.string(), z.any())),
      label: z.string().default('automation'),
    },
  },
  async ({ ops, label }) => text(await applyOps(ops, label)),
);

server.registerTool(
  'kernel_call',
  {
    description:
      'Call any kernel method directly (see kernel/m2c_kernel/commands). Params in camelCase ' +
      'wire format. For experts; prefer the specific tools.',
    inputSchema: {
      method: z.string(),
      params: z.record(z.string(), z.any()).default({}),
      lane: z.string().optional(),
    },
  },
  async ({ method, params, lane }) => text(await kernel(method, params, lane)),
);

server.registerTool(
  'list_commands',
  { description: 'Commands of the app (menus, views, tools) with their ids and availability.' },
  async () => text(await ui({ type: 'listCommands' })),
);

server.registerTool(
  'run_command',
  {
    description: 'Run an app command by id, e.g. a standard view, undo, or opening a tool.',
    inputSchema: { id: z.string() },
  },
  async ({ id }) => text(await ui({ type: 'runCommand', id })),
);

server.registerTool(
  'screenshot',
  { description: 'Screenshot of the Mesh-to-CAD window as the user sees it.' },
  async () => {
    const image = await rpc('screenshot');
    return { content: [{ type: 'image', data: image.data, mimeType: image.mimeType }] };
  },
);

await server.connect(new StdioServerTransport());
