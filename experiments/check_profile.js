// Decode the lossy-DCT-profile (tag 4) vectors with the shipped codec.js and assert
// bit-exact against the codec.py encoder. Mirrors check_vectors.js.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const Codec = require(path.join(__dirname, '..', 'codec.js'));
(async () => {
  const d = path.join(__dirname, 'vectors');
  const meta = JSON.parse(fs.readFileSync(path.join(d, 'profile_meta.json')));
  const buf = new Uint8Array(fs.readFileSync(path.join(d, 'profile.bin')));
  const dec = Codec.makeDecoder(3); const dv = new DataView(buf.buffer); let off = 0; const shas = [];
  while (off + 4 <= buf.length) { const len = dv.getUint32(off, false); off += 4;
    const r = await dec.decode(buf.subarray(off, off + len)); off += len;
    shas.push(crypto.createHash('sha256').update(Buffer.from(r.frame)).digest('hex')); }
  const ok = shas.length === meta.frame_shas.length && shas.every((s, i) => s === meta.frame_shas[i]);
  console.log('profile frames ' + shas.length + '/' + meta.nframes + ' : ' + (ok ? 'BIT-EXACT OK' : 'FAIL'));
  process.exit(ok ? 0 : 1);
})();
