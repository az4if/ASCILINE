"""
Tests for the live player UI backend bit we added.

Just the new stuff: the scrub sprite endpoint that powers the hover thumbnails.
The control bar itself is frontend, so it isn't covered here. Makes its own tiny
video and never touches your real files. The ffmpeg parts skip themselves if
ffmpeg isn't around.

    python -m unittest discover -s test
    pytest test/
"""
import os
import sys
import json
import shutil
import asyncio
import tempfile
import unittest

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stream_server as ss


def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def _make_video(path, frames=40, w=64, h=48, fps=10.0):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))
    if not vw.isOpened():
        return False

    for i in range(frames):
        img = np.zeros((h, w, 3), np.uint8)
        img[:, : w // 2] = (40, 80, 120)
        img[:, w // 2 :] = (120, 80, 40)
        x = (i * 2) % max(1, w - 8)
        img[h // 2 : h // 2 + 8, x : x + 8] = (255, 255, 255)
        vw.write(img)

    vw.release()
    return os.path.exists(path) and os.path.getsize(path) > 0


def _entry(video):
    return {"video": video, "mode": 5, "pixel": False, "cols": 80, "rows": 0, "vol": 1}


class ScrubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="asciline_ui_")
        cls.video = os.path.join(cls.tmp, "clip.avi")
        if not _make_video(cls.video):
            raise unittest.SkipTest("OpenCV could not write a test video here.")
        ss.app.state.queue = [_entry(cls.video)]
        ss.app.state.current_index = 0
        ss._scrub_cache.clear()

    @classmethod
    def tearDownClass(cls):
        ss._scrub_cache.clear()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_video_path_lookup(self):
        self.assertEqual(ss._scrub_video_path(0), self.video)
        # an out of range index just falls back to the current entry
        self.assertEqual(ss._scrub_video_path(99), self.video)

    def test_missing_video_says_unavailable(self):
        ss.app.state.queue = [_entry(os.path.join(self.tmp, "nope.mp4"))]
        try:
            body = json.loads(asyncio.run(ss.scrub_meta(0)).body)
            self.assertFalse(body["available"])
        finally:
            ss.app.state.queue = [_entry(self.video)]

    def test_thumbnails_can_be_disabled(self):
        ss.app.state.thumbnails = False
        try:
            body = json.loads(asyncio.run(ss.scrub_meta(0)).body)
            self.assertFalse(body["available"])
        finally:
            ss.app.state.thumbnails = True

    def test_sprite_404_before_it_is_built(self):
        from fastapi import HTTPException
        ss._scrub_cache.clear()
        with self.assertRaises(HTTPException):
            asyncio.run(ss.scrub_sprite(0))

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not installed")
    def test_sprite_grid_and_image(self):
        import math
        built = ss._build_scrub_sprite(self.video, max_count=16, cell_w=80)
        self.assertIsNotNone(built)

        m = built["meta"]
        self.assertTrue(m["available"])
        self.assertEqual(m["gridCols"], math.ceil(math.sqrt(m["count"])))
        self.assertGreaterEqual(m["gridCols"] * m["gridRows"], m["count"])

        # the bytes really are a JPEG, and it decodes to the full grid size
        arr = cv2.imdecode(np.frombuffer(built["jpeg"], np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(arr)
        self.assertEqual(arr.shape[0], m["gridRows"] * m["cellH"])
        self.assertEqual(arr.shape[1], m["gridCols"] * m["cellW"])

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not installed")
    def test_endpoint_builds_then_serves(self):
        ss._scrub_cache.clear()
        body = json.loads(asyncio.run(ss.scrub_meta(0)).body)
        self.assertTrue(body["available"])
        self.assertIn("sprite", body)

        # it's cached now, so the sprite serves as jpeg bytes
        resp = asyncio.run(ss.scrub_sprite(0))
        self.assertEqual(resp.media_type, "image/jpeg")
        self.assertGreater(len(resp.body), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
