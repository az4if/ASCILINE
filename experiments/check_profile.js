/**
 * Profile-specific checks for the lossy DCT profile (tag 4). The vectors live in the
 * standard experiments/vectors/ layout, so check_vectors.js already proves them
 * bit-exact; this script adds the one invariant a plain vector check cannot express.
 */
const fs = require('fs');
const path = require('path');
const codec = require('../codec.js');
const dir = path.join(__dirname, 'vectors', 'profile_qf70');

function readChunks(buf) {
  const out = []; let off = 0;
  while (off + 4 <= buf.length) { const len = buf.readUInt32BE(off); off += 4;
    out.push(new Uint8Array(buf.subarray(off, off + len))); off += len; }
  return out;
}
const same = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

(async () => {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json')));
  const msgs = readChunks(fs.readFileSync(path.join(dir, 'adaptive.bin')));
  const truth = readChunks(fs.readFileSync(path.join(dir, 'truth.bin')));

  const dec = codec.makeDecoder(meta.cellBytes);
  let ok = true;
  for (let i = 0; i < msgs.length; i++) ok = same((await dec.decode(msgs[i])).frame, truth[i]) && ok;
  console.log(`profile tag 4        ${String(msgs.length).padStart(3)} frames  ${ok ? 'PASS bit-exact' : 'FAIL'}`);

  // The profile decoder reuses module-level scratch across blocks to keep the hot path
  // allocation-free. That is only sound because its block loop never awaits, so two
  // decoders can never interleave inside it. Guard the invariant rather than trust it.
  const a = codec.makeDecoder(meta.cellBytes), b = codec.makeDecoder(meta.cellBytes);
  let conc = true;
  for (let i = 0; i < msgs.length; i++) {
    const [ra, rb] = await Promise.all([a.decode(msgs[i]), b.decode(msgs[i])]);
    conc = same(ra.frame, truth[i]) && same(rb.frame, truth[i]) && conc;
  }
  console.log(`concurrent decoders  ${String(msgs.length).padStart(3)} frames  ${conc ? 'PASS shared scratch safe' : 'FAIL'}`);
  process.exit(ok && conc ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
