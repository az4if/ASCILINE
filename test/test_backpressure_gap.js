/**
 * Backpressure frame-drop correctness test (issue #30).
 *
 * Proves the claim behind server-side frame dropping: when the server drops
 * frames for a slow client, it holds prev_frame across the gap, so the next
 * SENT frame is a delta against the last sent frame. Decoding through the
 * SHIPPED codec.js must reconstruct that post-gap frame bit-exact, identical to
 * the no-drop path -- the client just decodes fewer frames to get there.
 *
 * Encoding is done by codec.py via _gap_fixture.py (the encoder only exists in
 * Python); decoding uses codec.js, so this exercises the real Python<->JS path.
 *
 * Usage: node test/test_backpressure_gap.js
 */
const { execFileSync } = require('child_process');
const path = require('path');
const codec = require('../codec.js');

function b64ToU8(s) {
  return new Uint8Array(Buffer.from(s, 'base64'));
}

async function decodeLast(messagesB64, cellBytes) {
  const decoder = codec.makeDecoder(cellBytes);
  let last = null;
  for (const m of messagesB64) {
    // decode() expects an ArrayBuffer (as WebSocket delivers); give it a fresh one.
    const u8 = b64ToU8(m);
    const ab = u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength);
    last = (await decoder.decode(ab)).frame;
  }
  return last;
}

function eq(a, b) {
  if (a.length !== b.length) return { ok: false, why: `len ${a.length} != ${b.length}` };
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return { ok: false, why: `byte ${i}: ${a[i]} != ${b[i]}` };
  }
  return { ok: true };
}

(async () => {
  const fixturePath = path.join(__dirname, '_gap_fixture.py');
  const raw = execFileSync('python3', [fixturePath], { encoding: 'utf8' });
  const fx = JSON.parse(raw);

  const expected = b64ToU8(fx.expected);
  const checks = [];

  // 1. Drop path reconstructs frame 4 bit-exact (prev_frame held across the gap).
  const dropFrame = await decodeLast(fx.drop.messages, fx.cellBytes);
  const dropEq = eq(dropFrame, expected);
  checks.push(['drop path decodes frame 4 bit-exact', dropEq.ok, dropEq.why]);

  // 2. The post-gap frame is a real DELTA, not a fallback keyframe -- otherwise
  //    we wouldn't be exercising the held-prev_frame delta path at all.
  checks.push([
    'post-gap frame is a DELTA (tag 2)',
    fx.drop.gapTag === fx.delta_tag,
    `gapTag=${fx.drop.gapTag} expected=${fx.delta_tag}`,
  ]);

  // 3. No-drop path also reconstructs frame 4 bit-exact (sanity / same endpoint).
  const fullFrame = await decodeLast(fx.full.messages, fx.cellBytes);
  const fullEq = eq(fullFrame, expected);
  checks.push(['full path decodes frame 4 bit-exact', fullEq.ok, fullEq.why]);

  // 4. The win: drop path makes the client decode strictly fewer frames.
  checks.push([
    'drop path sends fewer frames than full path',
    fx.drop.messages.length < fx.full.messages.length,
    `drop=${fx.drop.messages.length} full=${fx.full.messages.length}`,
  ]);

  let failed = 0;
  for (const [name, ok, why] of checks) {
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + why}`);
    if (!ok) failed++;
  }
  console.log(`\n${checks.length - failed}/${checks.length} passed`);
  process.exit(failed === 0 ? 0 : 1);
})().catch((e) => { console.error('ERROR', e); process.exit(2); });
