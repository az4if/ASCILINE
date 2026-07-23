# Contributing to ASCILINE

This guide reflects lessons learned from real issues encountered during
ASCILINE's development, rather than a generic contribution template.
Please read it in full before contributing to the project.

## 1. Codec format vs. codec usage — know which one you're touching

There are three files involved in encoding/decoding: `codec.py` (encoder,
used by both the live server and `compiler.py`), the root
`codec.js` (decoder for the live stream), and `static_player/codec.js`
(decoder for the static player and Studio). The two JS files are separate
on purpose — `static_player` needs to work standalone, without the rest of
the repo. But "separate files" doesn't mean "free to diverge everywhere."
Only one part of them is allowed to drift independently; the rest has to
stay identical. Which is which:

**Format/decode layer — must stay bit-identical across all three files:**

- Tag numbers and their meaning (RAW, ZLIB, DELTA, RLE_FULL, DCT, ...)
- Header layout (magic bytes, field order, field sizes)
- DCT constants, quantization tables, YUV↔BGR formulas, anything that has
  to reproduce the exact same math on both sides

If you change any of this in `codec.py`, both `codec.js` copies need the
matching update in the same PR. If you change it in one `codec.js`, check
whether the other one decodes the same bitstream and needs the same fix.

**Usage/runtime layer — free to diverge, and already does:**

- Buffer management, backpressure reporting, jitter buffer size
- Whether frames are dropped after render (live, static player) or held
  entirely in memory (Studio's `bufferAll`)
- Seek bar behavior, UI-specific state

Don't "fix" a usage-layer difference by unifying it across live/static —
that divergence is intentional. Do treat any format-layer difference as a
bug.

**Non-negotiable for any format PR:** if you add or change a tag, header
field, or wire-level encoding, the PR must include a vector test — under
`experiments/`, encode with `codec.py` and decode with the JS side (or vice
versa), then assert byte-for-byte equality. Note what this does and doesn't
catch: it verifies encode/decode correctness for the exact cases you feed
it, nothing more. It won't catch a race condition, a performance
regression, or an integration bug (state mutation, buffer sizing) outside
the encode/decode path itself — those need their own testing, not a vector
test. We're strict about this specific check because it's the one that's
gone wrong silently before: a PR claimed "verified bit-exact" with no
runnable proof, and the gap only surfaced in review.

**Not every tag is in the same race.** RAW, ZLIB, DELTA, and RLE_FULL
compete per-frame for smallest size — both live streaming and the static
compiler use that comparison. DCT (tag 4, enabled via the `--profile` flag)
is different: it's
opt-in and exclusive, not a competitor in that race, and currently only
reachable through `compiler.py` — the live server
(`stream_server.py`) never produces it. If you're adding decoder support
for a tag, check which side(s) actually need to produce or consume it
before assuming all decoders must handle everything symmetrically.

**Renumbering existing constants (tag values, mode numbers, quantization
tiers) is a breaking change even if it "still works."** Prefer adding a new
value over reassigning an existing one. If reassignment is unavoidable,
say so explicitly in the PR description — a silent meaning change (e.g.
"mode 2 now means something different") breaks existing scripts, playlists,
and muscle memory without any error message.

## 2. Backward compatibility is the default assumption

New features should not require existing clients or existing files to
change behavior. In practice this means:

- Gate new wire behavior behind an opt-in (query param, flag) the way the
  adaptive codec uses `?codec=adaptive` — the absence of the flag must
  reproduce the old behavior byte-for-byte.
- If a file format changes (see `ASCF` → `ASC2`), branch the reader on the
  magic bytes so old files keep playing, even if they don't get the new
  feature (e.g. duration display).
- Never assume "nobody uses the old path anymore" — verify, or keep it.

## 3. Watch for race conditions in the WebSocket handler

`websocket_endpoint` looks risky at first glance: `receive_commands()` runs
as a separate task while frames are produced via `run_in_executor`, so it
looks like two things could touch the same state at once. Right now it's
safe, for a specific reason worth understanding before you touch this
code:

1. `receive_commands()` does exactly one thing: `await cmd_queue.put(msg)`.
   It never touches decoder state, buffers, or `prev_frame` itself.
2. The main loop drains `cmd_queue` (pause/seek/filter/reinit/...) at the
   top of each iteration, before calling `produce()`.
3. The main loop always `await`s `produce()` to finish before draining the
   queue again.

So the only place any state actually gets mutated is the main loop, and it
never does so while `produce()` is running. That ordering is what currently
keeps this safe — there's no lock, no atomic anything, just this sequence.

This isn't a mandate to keep the architecture exactly as-is forever — if
you have a good reason to restructure how commands and frame production
interact, that's a legitimate thing to propose. The point of this section
is just to make sure you're doing it deliberately: if your change adds a
new command type or touches shared state (decoder, buffers, `prev_frame`)
from a task other than the main loop, stop and think through the ordering
explicitly, rather than assuming it's fine because nothing crashes in a
quick test. The failure mode here isn't an immediate crash — it's an
occasional corrupted frame under real-world timing that a fast manual test
won't catch.

## 4. Before opening a PR

Run whatever's actually relevant to your change — not everything, every
time. A CSS tweak doesn't need the codec vector tests run against it.

- Touching codec.py or either codec.js? Run pytest test/ plus the
  relevant experiments/_.js / _.py vector scripts. If your change adds
  or changes a tag, header field, or wire-level encoding, running existing
  tests isn't enough — you must provide a runnable proof (e.g., a new vector
  test script under experiments/) demonstrating that it round-trips correctly
  (see §1). This is the one case in this whole document where skipping is not okay.

- Touching `stream_server.py`'s WebSocket handler (new command type, seek,
  reinit, pause)? Manually trigger the same command a few times in quick
  succession, before the previous one has visibly resolved — this exact
  stress pattern has exposed real bugs here before that normal use didn't.
- Anything else (styling, docs, UI-only changes) — normal manual testing
  is enough, no special ceremony.

If you disagree with something in this document — you think a rule doesn't
apply to your change, or that what you're doing actually improves the
architecture rather than risking it — you can still open the PR. Just
start the description with `Deviation:` and explain why. That's enough;
no approval needed in advance, just don't skip the explanation.
