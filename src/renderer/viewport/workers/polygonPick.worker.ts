// Worker: lasso and rectangle picking on large scans (docs/ARCHITECTURE.md 5.8).
// It lives as long as the scan. The centroids and face normals arrive once from
// the preparation worker through a MessagePort; each query then carries only the
// polygon, the view, the hidden faces and, for visible-only picking, the face ids.

import type { PolygonPickReply, PolygonPickRequest, PolygonPickScan } from './messages';
import { pickFacesInPolygon } from './polygonPick';

let scan: PolygonPickScan | null = null;
const waiting: PolygonPickRequest[] = [];

const reply = (message: PolygonPickReply) => {
  const transfer = message.faces ? [message.faces.buffer] : [];
  (self as unknown as Worker).postMessage(message, transfer);
};

function answer(request: PolygonPickRequest, data: PolygonPickScan): void {
  try {
    reply({
      id: request.id,
      faces: pickFacesInPolygon(request.query, data.centroids, data.faceNormals),
    });
  } catch (error) {
    reply({ id: request.id, faces: null, error: String(error) });
  }
}

self.onmessage = (event: MessageEvent<{ port: MessagePort } | PolygonPickRequest>) => {
  const message = event.data;
  if ('port' in message) {
    message.port.onmessage = (scanEvent: MessageEvent<PolygonPickScan>) => {
      const data = scanEvent.data;
      scan = data;
      for (const request of waiting.splice(0)) answer(request, data);
    };
    return;
  }
  if (scan) answer(message, scan);
  else waiting.push(message);
};
