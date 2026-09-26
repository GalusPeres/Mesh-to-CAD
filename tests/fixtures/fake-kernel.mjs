// A protocol-speaking stand-in for the Python kernel, used by the main-process
// tests. It implements the frame format independently of src/shared, so the tests
// also check that both sides agree.
//
// Methods: echo, sleep ({ ms }, cooperative), hang ({ ms }, ignores cancel like a
// native call holding the GIL), progress ({ steps }), crash, system.shutdown.
// FAKE_KERNEL_PROTOCOL overrides the protocol version reported in `ready`.

const MAGIC = Buffer.from('M2CF');
const pad = (length) => (8 - (length % 8)) % 8;

function writeFrame(header, buffers = []) {
  const head = Buffer.from(
    JSON.stringify({ ...header, buffers: buffers.map((b) => b.length) }),
    'utf8',
  );
  const headPad = pad(12 + head.length);
  const body = Buffer.concat(
    buffers.flatMap((buffer) => [buffer, Buffer.alloc(pad(buffer.length))]),
  );
  const prefix = Buffer.alloc(12);
  MAGIC.copy(prefix, 0);
  prefix.writeUInt32LE(head.length, 4);
  prefix.writeUInt32LE(body.length, 8);
  process.stdout.write(Buffer.concat([prefix, head, Buffer.alloc(headPad), body]));
}

const respond = (id, result, buffers) =>
  writeFrame({ type: 'response', id, ok: true, result }, buffers);
const fail = (id, code) =>
  writeFrame({ type: 'response', id, ok: false, error: { code, params: {} } });

const cancelled = new Set();
const busyUntil = { time: 0 };

function handle(header, buffers) {
  if (header.type === 'cancel') {
    cancelled.add(header.id);
    return;
  }
  const { id, method, params } = header;
  switch (method) {
    case 'echo':
      respond(id, { params, origin: header.origin, lane: header.lane ?? null }, buffers);
      break;
    case 'sleep': {
      const end = Date.now() + (params.ms ?? 0);
      const tick = () => {
        if (cancelled.has(id)) return fail(id, 'kernel.cancelled');
        if (Date.now() >= end) return respond(id, { slept: params.ms });
        setTimeout(tick, 5);
      };
      tick();
      break;
    }
    case 'hang':
      busyUntil.time = Date.now() + (params.ms ?? 0);
      setTimeout(() => respond(id, { hung: params.ms }), params.ms ?? 0);
      break;
    case 'progress':
      for (let step = 1; step <= (params.steps ?? 1); step += 1) {
        writeFrame({
          type: 'event',
          event: 'progress',
          requestId: id,
          data: { fraction: step / params.steps, stage: 'kernel.working' },
        });
      }
      respond(id, { steps: params.steps });
      break;
    case 'crash':
      process.exit(3);
      break;
    case 'system.shutdown':
      respond(id, {});
      process.exit(0);
      break;
    default:
      fail(id, 'kernel.unknownMethod');
  }
}

let pending = Buffer.alloc(0);
process.stdin.on('data', (chunk) => {
  pending = Buffer.concat([pending, chunk]);
  for (;;) {
    if (pending.length < 12) return;
    const headerLength = pending.readUInt32LE(4);
    const bodyLength = pending.readUInt32LE(8);
    const headerEnd = 12 + headerLength;
    const total = headerEnd + pad(headerEnd) + bodyLength;
    if (pending.length < total) return;
    const header = JSON.parse(pending.subarray(12, headerEnd).toString('utf8'));
    const body = pending.subarray(headerEnd + pad(headerEnd), total);
    const buffers = [];
    let offset = 0;
    for (const size of header.buffers ?? []) {
      buffers.push(Buffer.from(body.subarray(offset, offset + size)));
      offset += size + pad(size);
    }
    pending = pending.subarray(total);
    handle(header, buffers);
  }
});
process.stdin.on('end', () => process.exit(0));

const protocolVersion = Number(process.env.FAKE_KERNEL_PROTOCOL ?? 1);
writeFrame({
  type: 'event',
  event: 'ready',
  data: { protocolVersion, kernelVersion: 'fake', pythonVersion: 'none' },
});
