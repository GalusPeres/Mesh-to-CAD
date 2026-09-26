import { type Session, app } from 'electron';

const BASE_POLICY = [
  "default-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
];

/** Content Security Policy of the packaged renderer. */
export const PRODUCTION_CSP = [...BASE_POLICY, "script-src 'self'", "connect-src 'self'"].join(
  '; ',
);

/** The Vite dev server needs an inline preamble and a websocket for hot reload. */
export function developmentCsp(devOrigin: string): string {
  const socket = devOrigin.replace(/^http/, 'ws');
  return [...BASE_POLICY, "script-src 'self' 'unsafe-inline'", `connect-src 'self' ${socket}`].join(
    '; ',
  );
}

const DEV_URL = /^http:\/\/127\.0\.0\.1:\d+\/?$/;

/** The dev renderer URL, accepted only for unpackaged builds and only on 127.0.0.1. */
export function developmentUrl(): string | null {
  const url = process.env.ELECTRON_RENDERER_URL;
  if (app.isPackaged || !url) return null;
  if (!DEV_URL.test(url)) throw new Error('Only a local Vite dev server on 127.0.0.1 is allowed.');
  return url;
}

/** Deny every permission and block navigation, new windows and webviews. */
export function hardenSession(session: Session, devOrigin: string | null): void {
  session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.setPermissionCheckHandler(() => false);
  if (devOrigin) {
    const policy = developmentCsp(devOrigin);
    session.webRequest.onHeadersReceived({ urls: [`${devOrigin}/*`] }, (details, callback) => {
      callback({
        responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [policy] },
      });
    });
  }
  app.on('web-contents-created', (_event, contents) => {
    contents.setWindowOpenHandler(() => ({ action: 'deny' }));
    contents.on('will-navigate', (event) => event.preventDefault());
    contents.on('will-redirect', (event) => event.preventDefault());
    contents.on('will-attach-webview', (event) => event.preventDefault());
  });
}
