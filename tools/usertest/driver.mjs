// What a user test does with the app: click buttons, press keys, move the mouse in the
// 3D view at part coordinates, wait for the tool, look (screenshots) and check numbers.

import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** The user's hands and eyes on the app behind `client`; screenshots go to `out`. */
export function createDriver(client, out) {
  mkdirSync(out, { recursive: true });
  const failures = [];
  const { ui } = client;

  /** Where a part point (mm) is on the screen. */
  async function at(point) {
    const [screen] = await ui({ type: 'project', points: [point] });
    if (!screen) throw new Error(`not on screen: ${point.join(', ')}`);
    return screen;
  }

  const pointer = (kind, { x, y }, mods = {}) => ui({ type: 'pointer', kind, x, y, ...mods });

  /** Move the mouse there and let hover feedback appear. */
  async function hover(screen) {
    await pointer('move', screen);
    await pause(250);
  }

  /** A left click (or `button: 2` for right) at a screen point, mouse moved there first. */
  async function tap(screen, mods = {}) {
    await pointer('move', screen, mods);
    await pause(150);
    await pointer('down', screen, mods);
    await pointer('up', screen, mods);
    await pause(250);
  }

  /** Press at `from`, move in steps to `to`, release. */
  async function drag(from, to, mods = {}, steps = 14) {
    await hover(from);
    await pointer('down', from, mods);
    for (let i = 1; i <= steps; i += 1) {
      const t = i / steps;
      await pointer(
        'move',
        { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t },
        mods,
      );
      await pause(40);
    }
    await pointer('up', to, mods);
    await pause(250);
  }

  async function key(name, mods = {}) {
    await ui({ type: 'key', key: name, ...mods });
    await pause(300);
  }

  /** Click a button by test id or label. */
  async function press(target) {
    await ui({ type: 'click', target });
    await pause(300);
  }

  async function command(id) {
    await ui({ type: 'runCommand', id });
    await pause(300);
  }

  /** The open tool's automation info (net, border edges with screen positions, state). */
  const toolInfo = () => ui({ type: 'toolInfo' });

  /** Revision, open tool and selected triangle count of the app. */
  const state = () => ui({ type: 'state' });

  /** What the pointer finds at a screen point: scan, body, edge or item. */
  const pick = (screen) => ui({ type: 'pick', x: screen.x, y: screen.y });

  /** Wait until the open tool has no job running (fit, deviation, build). */
  async function settle(timeoutMs = 120_000) {
    const end = Date.now() + timeoutMs;
    await pause(400);
    while (Date.now() < end) {
      const info = await toolInfo();
      if (!info?.state?.job) {
        await pause(300);
        return;
      }
      await pause(250);
    }
    throw new Error('the tool is still busy');
  }

  async function shot(name) {
    const { data } = await client.rpc('screenshot');
    const file = path.join(out, `${name}.png`);
    writeFileSync(file, Buffer.from(data, 'base64'));
    console.log(`     ${file}`);
  }

  function check(name, ok, detail = '') {
    console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? `  (${detail})` : ''}`);
    if (!ok) failures.push(name);
    return ok;
  }

  /** Poll `probe` until it returns something truthy. */
  async function until(probe, what, timeoutMs = 120_000) {
    const end = Date.now() + timeoutMs;
    while (Date.now() < end) {
      const value = await probe();
      if (value) return value;
      await pause(500);
    }
    throw new Error(`timed out waiting for ${what}`);
  }

  return {
    at,
    hover,
    tap,
    drag,
    key,
    press,
    command,
    toolInfo,
    state,
    pick,
    settle,
    until,
    shot,
    check,
    kernel: client.kernel,
    failures,
  };
}
