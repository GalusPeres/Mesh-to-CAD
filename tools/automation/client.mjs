// Client for the running application's local automation interface (docs/AUTOMATION.md),
// shared by the MCP server and the user tests. The application publishes port and token
// in automation.json in its user data folder once automation is allowed in the settings
// (or it was started with M2C_AUTOMATION=1).

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const PRODUCT = 'Mesh-to-CAD';

/** The app instance named by `M2C_INSTANCE`, or null for the default profiles. */
export const INSTANCE = process.env.M2C_INSTANCE?.replace(/[^\w-]/g, '') || null;

/**
 * Profiles the app may run with: the user's and the automation profile, or with
 * `M2C_INSTANCE` only that instance's automation profile (several apps side by side).
 */
const PROFILES = INSTANCE
  ? [`${PRODUCT}-automation-${INSTANCE}`]
  : [PRODUCT, `${PRODUCT}-automation`];

/**
 * Where the app may have published automation.json. Besides %APPDATA%, apps that
 * run inside an MSIX package (such as the Claude desktop app, which may also have
 * started Mesh-to-CAD) see a per-package copy of AppData.
 */
function infoCandidates() {
  if (process.env.M2C_AUTOMATION_INFO) return [process.env.M2C_AUTOMATION_INFO];
  const home = os.homedir();
  const appData = process.env.APPDATA ?? path.join(home, 'AppData', 'Roaming');
  const localAppData = process.env.LOCALAPPDATA ?? path.join(home, 'AppData', 'Local');
  const candidates = PROFILES.map((profile) => path.join(appData, profile, 'automation.json'));
  const packages = path.join(localAppData, 'Packages');
  if (existsSync(packages)) {
    for (const name of readdirSync(packages)) {
      for (const profile of PROFILES) {
        candidates.push(
          path.join(packages, name, 'LocalCache', 'Roaming', profile, 'automation.json'),
        );
      }
    }
  }
  return candidates;
}

function processAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/** Port and token of the running app: the newest automation.json whose process is alive. */
function connection() {
  const live = infoCandidates()
    .filter((file) => existsSync(file))
    .map((file) => ({ info: JSON.parse(readFileSync(file, 'utf8')), time: statSync(file).mtimeMs }))
    .filter(({ info }) => processAlive(info.pid))
    .sort((a, b) => b.time - a.time);
  if (live.length === 0) {
    throw new Error(
      `${PRODUCT} is not reachable. Start the app and enable "Steuerung durch KI-Assistenten ` +
        `erlauben (MCP)" in Datei > Einstellungen > Automatisierung.`,
    );
  }
  return live[0].info;
}

/**
 * The requests a client sends. `signal` returns the abort signal of the call in
 * progress, if any: when the caller gives up, the request to the app is aborted too,
 * and the app cancels the kernel job instead of letting it block every later edit.
 */
export function automationClient(signal = () => undefined) {
  /** One request to the application's automation interface. */
  async function rpc(method, params = {}) {
    const { port, token } = connection();
    const response = await fetch(`http://127.0.0.1:${port}/rpc`, {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify({ method, params }),
      signal: signal(),
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
  return { rpc, kernel, ui };
}
