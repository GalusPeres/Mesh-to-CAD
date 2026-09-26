import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { net, protocol } from 'electron';

export const APP_ORIGIN = 'm2c://app';
export const APP_URL = `${APP_ORIGIN}/index.html`;

/** Must run before the app is ready. */
export function registerAppScheme(): void {
  protocol.registerSchemesAsPrivileged([
    {
      scheme: 'm2c',
      privileges: { standard: true, secure: true, supportFetchAPI: true, codeCache: true },
    },
  ]);
}

/**
 * Serve the built renderer from `m2c://app/`. Pages never load from `file://`;
 * requests that resolve outside the renderer directory are refused.
 */
export function serveRenderer(rendererDirectory: string, contentSecurityPolicy: string): void {
  const root = path.resolve(rendererDirectory);
  protocol.handle('m2c', async (request) => {
    const url = new URL(request.url);
    if (url.host !== 'app') return new Response('Forbidden', { status: 403 });
    const relative = decodeURIComponent(url.pathname);
    const target = path.resolve(root, `.${relative === '/' ? '/index.html' : relative}`);
    if (!target.startsWith(root + path.sep)) return new Response('Forbidden', { status: 403 });
    const file = await net.fetch(pathToFileURL(target).href).catch(() => null);
    if (!file?.ok) return new Response('Not found', { status: 404 });
    const headers = new Headers(file.headers);
    headers.set('Content-Security-Policy', contentSecurityPolicy);
    headers.set('X-Content-Type-Options', 'nosniff');
    return new Response(file.body, { status: 200, headers });
  });
}
