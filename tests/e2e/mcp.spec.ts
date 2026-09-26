// The MCP server (tools/mcp/server.mjs) drives the real application through the
// local automation interface: load a scan, align, fit the top face, surface it,
// export STEP and take a screenshot, as an AI assistant would.

import { existsSync, mkdtempSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { expect, test } from '@playwright/test';

import { ROOT, launchApp } from './support/app';
import { writeTorusStl } from './support/meshes';

type ToolResult = { content: { type: string; text?: string; data?: string }[]; isError?: boolean };

function json(result: ToolResult): Record<string, unknown> {
  expect(result.isError, result.content[0]?.text).toBeFalsy();
  return JSON.parse(result.content[0]?.text ?? '{}') as Record<string, unknown>;
}

test('an MCP client loads, aligns, fits, surfaces and exports through the running app', async () => {
  test.setTimeout(300_000);
  const work = mkdtempSync(path.join(tmpdir(), 'm2c-mcp-'));
  const stl = path.join(work, 'torus.stl');
  writeTorusStl(stl, 120, 48);

  process.env.M2C_AUTOMATION = '1';
  const { app, page } = await launchApp();
  delete process.env.M2C_AUTOMATION;
  const userData = await app.evaluate(({ app: electronApp }) => electronApp.getPath('userData'));
  const info = path.join(userData, 'automation.json');
  await expect.poll(() => existsSync(info)).toBe(true);

  const client = new Client({ name: 'mesh-to-cad-e2e', version: '1.0.0' });
  await client.connect(
    new StdioClientTransport({
      command: process.execPath,
      args: [path.join(ROOT, 'tools', 'mcp', 'server.mjs')],
      env: { ...(process.env as Record<string, string>), M2C_AUTOMATION_INFO: info },
    }),
  );
  const call = (name: string, args: Record<string, unknown> = {}) =>
    client.callTool({ name, arguments: args }) as Promise<ToolResult>;

  try {
    const tools = (await client.listTools()).tools.map((tool) => tool.name);
    expect(tools).toEqual(expect.arrayContaining(['app_status', 'import_scan', 'fit_shape']));

    const imported = json(await call('import_scan', { path: stl }));
    expect(imported.trianglesInFile).toBe(2 * 120 * 48);
    await expect(page.getByRole('treeitem', { name: /torus.stl/ })).toBeVisible();

    json(await call('align_auto'));
    const bounds = json(await call('scan_bounds')) as { min: number[]; max: number[] };

    // The top of the torus: the triangles near the highest point, facing up.
    const top = bounds.max[2]!;
    const fitted = json(
      await call('fit_shape', {
        min: [bounds.min[0], bounds.min[1], top - 0.5],
        max: [bounds.max[0], bounds.max[1], top + 0.1],
        facing: [0, 0, 1],
        maxAngleDeg: 15,
        kind: 'plane',
      }),
    );
    expect(fitted.kind).toBe('plane');

    const surfaced = json(await call('auto_surface', { detail: 'coarse' })) as {
      bodies: { valid: boolean }[];
    };
    expect(surfaced.bodies.some((body) => body.valid)).toBe(true);

    const step = path.join(work, 'torus.step');
    json(await call('export_step', { path: step }));
    expect(statSync(step).size).toBeGreaterThan(10_000);

    const status = json(await call('app_status')) as {
      document: { features: { type: string; state: string }[] };
    };
    expect(status.document.features.map((feature) => feature.type)).toEqual(
      expect.arrayContaining(['fit', 'autoSurface']),
    );

    const shot = (await call('screenshot')).content[0]!;
    expect(shot.type).toBe('image');
    writeFileSync(path.join(work, 'screenshot.png'), Buffer.from(shot.data!, 'base64'));

    const commands = JSON.parse((await call('list_commands')).content[0]!.text!) as unknown[];
    expect(commands.length).toBeGreaterThan(10);
  } finally {
    await client.close();
    await app.close();
  }
});
