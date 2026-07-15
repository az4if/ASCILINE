# Encode lossy-DCT-profile (tag 4) test vectors with codec.py, using the same output
# layout as gen_vectors.py (experiments/vectors/<name>/ with meta.json, adaptive.bin
# and truth.bin) so check_vectors.js verifies the profile alongside the other vectors.
import os, sys, struct, json, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from codec import ProfileEncoder

W, H, N, QF = 160, 96, 40, 70
NAME = "profile_qf70"

def frame(i):
    yy, xx = np.mgrid[0:H, 0:W]
    B=(40+180*xx/W).astype(np.uint8); G=(30+150*yy/H).astype(np.uint8); R=np.full((H,W),60,np.uint8)
    bx=int((0.5+0.4*math.sin(i/N*2*math.pi))*(W-24)); by=int((0.5+0.4*math.cos(i/N*2*math.pi))*(H-24))
    R[by:by+24,bx:bx+24]=230; G[by:by+24,bx:bx+24]=230; B[by:by+24,bx:bx+24]=80
    return np.ascontiguousarray(np.stack([B,G,R],2).astype(np.uint8))

outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors", NAME)
os.makedirs(outdir, exist_ok=True)
enc = ProfileEncoder(W, H, QF)
fa = open(os.path.join(outdir, "adaptive.bin"), "wb")
ft = open(os.path.join(outdir, "truth.bin"), "wb")
raw_total = adapt_total = 0
for i in range(N):
    msg, shown = enc.encode(frame(i))
    # Truth = the encoder's intended frame, i.e. the lossy approximation the client
    # must reconstruct exactly, same convention as the tolerance vectors.
    body = bytes(shown)
    fa.write(struct.pack(">I", len(msg))); fa.write(msg)
    ft.write(struct.pack(">I", len(body))); ft.write(body)
    raw_total += 4 + len(body); adapt_total += len(msg)
fa.close(); ft.close()
json.dump({"cellBytes": 3, "nframes": N, "rows": H, "cols": W,
           "legacyBytes": raw_total, "adaptiveBytes": adapt_total},
          open(os.path.join(outdir, "meta.json"), "w"))
print(f"{NAME:28} {N} frames  legacy={raw_total/1024:7.0f}KB  "
      f"profile={adapt_total/1024:6.0f}KB ({adapt_total/raw_total:5.1%})")
