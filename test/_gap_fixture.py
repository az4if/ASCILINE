"""
Fixture generator for the backpressure frame-drop test (see test_backpressure_gap.js).

Emits JSON on stdout describing two encodings of the SAME synthetic frame
sequence, both ending on frame 4:

  drop  : keyframe(0), then frames 1-3 are DROPPED server-side (prev_frame held),
          then frame 4 encoded as a delta against frame 0's shown state.
  full  : every frame 0..4 encoded against the previous shown frame.

The decode side (codec.js, the shipped path) must reconstruct frame 4 bit-exact
in BOTH cases -- that is the correctness claim behind server-side dropping:
holding prev_frame across the gap keeps the delta chain exact. The drop case
must also send strictly fewer messages, which is the whole point.

Run standalone: python3 test/_gap_fixture.py
"""
import base64
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from codec import encode_frame, TAG_DELTA  # noqa: E402

ROWS, COLS, C = 8, 8, 4  # ASCII colour: [char, R, G, B]


def make_sequence():
    """Deterministic frames where only a few cells change each step, so the
    post-gap frame still differs from frame 0 by a small fraction (-> DELTA path)."""
    rng = np.random.default_rng(1234)
    base = rng.integers(0, 256, size=(ROWS, COLS, C), dtype=np.uint8)
    frames = [base.copy()]
    f = base.copy()
    for step in range(1, 5):
        f = f.copy()
        # Mutate one distinct cell per step (structure + colour), small delta.
        r, col = step % ROWS, (step * 3) % COLS
        f[r, col, 0] = (int(f[r, col, 0]) + 7 * step) % 256  # char plane
        f[r, col, 1:] = (f[r, col, 1:].astype(int) + 30 * step) % 256
        frames.append(f)
    return frames


def b64(buf: bytes) -> str:
    return base64.b64encode(buf).decode("ascii")


def main():
    frames = make_sequence()
    expected = frames[4]

    # ── DROP path: keyframe 0, drop 1-3 (hold prev), delta 4 vs frame 0 ──
    msg0, shown0 = encode_frame(frames[0], None, 0, tolerance=0)
    msg4_drop, _ = encode_frame(frames[4], shown0, 4, tolerance=0)
    drop_tag = msg4_drop[4]  # byte after the 4-byte frame index

    # ── FULL path: every frame against the previous shown ──
    full_msgs = []
    prev = None
    for i, fr in enumerate(frames):
        m, prev = encode_frame(fr, prev, i, tolerance=0)
        full_msgs.append(b64(m))

    out = {
        "cellBytes": C,
        "rows": ROWS,
        "cols": COLS,
        "expected": b64(expected.tobytes()),
        "drop": {"messages": [b64(msg0), b64(msg4_drop)], "gapTag": drop_tag},
        "full": {"messages": full_msgs},
        "delta_tag": TAG_DELTA,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
