"""Smoke-test a built app: make a tagged JPEG, run the app's CLI on it, check the tags are gone.
    python tests/smoke_app.py <path to Tag executable>
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_core as t  # noqa: E402
from aitagremover import core  # noqa: E402

exe = sys.argv[1]
d = tempfile.mkdtemp()
c = t.ImageTests("test_jpeg_baseline")
c.setUp()
src = os.path.join(d, "tagged.jpg")
with open(src, "wb") as f:
    f.write(c._jpeg_tagged())
assert core.scan(src).ai_markers, "fixture should be tagged"
out = os.path.join(d, "out")
r = subprocess.run([exe, "clean", src, "-o", out], timeout=180)
dst = os.path.join(out, "tagged.jpg")
assert os.path.isfile(dst), "app produced no output (exit %s)" % r.returncode
left = core.scan(dst).ai_markers
assert not left, "tags left: %s" % left
# Video: proves the built app finds its bundled ffmpeg.
import struct  # noqa: E402

ff = core.find_ffmpeg()
if ff:
    vid = os.path.join(d, "clip.mp4")
    subprocess.check_call([ff, "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=1",
                           "-c:v", "mpeg4", "-metadata", "comment=Made with AI - Higgsfield", vid])
    body = bytes.fromhex("d8fec3d61b0e483c92975828877ec481") + t.JUMBF
    with open(vid, "ab") as f:
        f.write(struct.pack(">I", len(body) + 8) + b"uuid" + body)
    assert core.scan(vid).ai_markers, "video fixture should be tagged"
    env = dict(os.environ)
    env.pop("AITAG_FFMPEG", None)
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if "ffmpeg" not in p.lower())
    r = subprocess.run([exe, "clean", vid, "-o", out], timeout=180, env=env)
    vdst = os.path.join(out, "clip.mp4")
    assert os.path.isfile(vdst), "app produced no video output (exit %s)" % r.returncode
    assert not core.scan(vdst).ai_markers, "video tags left"
    print("video cleaned too")

print("smoke test passed: %s cleaned the file (exit %s)" % (exe, r.returncode))
