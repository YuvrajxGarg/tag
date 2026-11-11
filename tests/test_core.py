"""Run:  python3 -m unittest discover tests   (needs Pillow; video tests need ffmpeg)"""

import io
import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib


def read(path):
    with open(path, "rb") as f:
        return f.read()

from PIL import Image

from aitagremover import core

XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
    b'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/'
    b'compositeWithTrainedAlgorithmicMedia" xmp:CreatorTool="Adobe Photoshop 26.0 (Generative Fill, Firefly)"/>'
    b"</rdf:RDF></x:xmpmeta>"
)
JUMBF = b"\x00\x00\x00\x40jumb\x00\x00\x00\x18jumdc2pa\x00\x11\x00\x10" + b"contentauth Higgsfield manifest" + b"\x00" * 8


def seg(marker, payload):
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def png_chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def exif_with_orientation(o):
    im = Image.new("RGB", (1, 1))
    ex = im.getexif()
    ex[0x0112] = o
    ex[0x0131] = "Adobe Firefly"
    return ex.tobytes()


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.img = Image.new("RGB", (64, 48))
        for x in range(64):
            for y in range(48):
                self.img.putpixel((x, y), (x * 4, y * 5, (x * y) % 256))

    def _p(self, name):
        return os.path.join(self.tmp, name)

    def _check(self, src, expect_markers=True):
        before = core.scan(src)
        self.assertIsNone(before.error)
        if expect_markers:
            self.assertTrue(before.ai_markers, before.metadata_blocks)
        dst = self._p("cleaned/" + os.path.basename(src))
        after = core.clean(src, dst)
        self.assertIsNone(after.error)
        self.assertEqual(after.ai_markers, [])
        raw = read(dst).lower()
        for needle in (b"c2pa", b"firefly", b"higgsfield", b"algorithmicmedia", b"xmpmeta"):
            self.assertNotIn(needle, raw)
        a, b = Image.open(src), Image.open(dst)
        self.assertEqual(a.size, b.size)
        self.assertEqual(list(a.convert("RGBA").getdata()), list(b.convert("RGBA").getdata()))
        return dst

    def _jpeg_tagged(self, progressive=False, orientation=6):
        buf = io.BytesIO()
        self.img.save(buf, "JPEG", quality=90, progressive=progressive)
        data = buf.getvalue()
        extra = (
            seg(0xE1, exif_with_orientation(orientation))
            + seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP)
            + seg(0xEB, b"JP\x00\x00\x00\x00\x00\x01" + JUMBF)
            + seg(0xED, b"Photoshop 3.0\x00generative AI")
            + seg(0xFE, b"Made with AI")
        )
        return data[:2] + extra + data[2:] + b"trailing c2pa junk"

    def test_jpeg_baseline(self):
        p = self._p("a.jpg")
        open(p, "wb").write(self._jpeg_tagged())
        dst = self._check(p)
        self.assertEqual(Image.open(dst).getexif().get(0x0112), 6)  # orientation preserved
        self.assertEqual(len(Image.open(dst).getexif()), 1)  # but nothing else

    def test_jpeg_progressive(self):
        p = self._p("b.jpg")
        open(p, "wb").write(self._jpeg_tagged(progressive=True, orientation=1))
        dst = self._check(p)
        self.assertNotIn(0x0112, Image.open(dst).getexif())

    def test_jpeg_icc_kept(self):
        icc = b"\x00" * 128 + b"fake icc profile"
        buf = io.BytesIO()
        self.img.save(buf, "JPEG", icc_profile=icc)
        data = buf.getvalue()
        p = self._p("c.jpg")
        open(p, "wb").write(data[:2] + seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00" + XMP) + data[2:])
        dst = self._check(p)
        self.assertEqual(Image.open(dst).info.get("icc_profile"), icc)

    def test_png(self):
        buf = io.BytesIO()
        self.img.save(buf, "PNG")
        d = buf.getvalue()
        ihdr_end = 8 + 25
        extra = (
            png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + XMP)
            + png_chunk(b"caBX", JUMBF)
            + png_chunk(b"tEXt", b"parameters\x00stable diffusion prompt")
            + png_chunk(b"zTXt", b"Comment\x00\x00" + zlib.compress(b"Higgsfield soul"))
        )
        p = self._p("d.png")
        open(p, "wb").write(d[:ihdr_end] + extra + d[ihdr_end:] + b"junk")
        self._check(p)

    def test_webp(self):
        p = self._p("e.webp")
        self.img.save(p, "WEBP", lossless=True, exif=exif_with_orientation(1), xmp=XMP)
        dst = self._check(p)
        data = read(dst)
        self.assertEqual(struct.unpack("<I", data[4:8])[0], len(data) - 8)

    def test_clean_image_without_tags(self):
        p = self._p("plain.png")
        self.img.save(p, "PNG")
        self._check(p, expect_markers=False)

    def test_refuses_overwrite(self):
        p = self._p("x.png")
        self.img.save(p, "PNG")
        with self.assertRaises(ValueError):
            core.clean(p, p)


def _ffprobe():
    ff = core.find_ffmpeg()
    if not ff:
        return None
    sib = os.path.join(os.path.dirname(ff), "ffprobe" + (".exe" if os.name == "nt" else ""))
    return sib if os.path.isfile(sib) else shutil.which("ffprobe")


@unittest.skipUnless(core.find_ffmpeg() and _ffprobe(), "ffmpeg/ffprobe not available")
class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ff = core.find_ffmpeg()

    def _probe(self, path):
        out = subprocess.check_output([_ffprobe(), "-v", "error", "-show_format", "-show_streams", "-of", "json", path])
        return json.loads(out)

    def _make(self, ext):
        src = os.path.join(self.tmp, "raw" + ext)
        vcodec = ["-c:v", "libvpx-vp9"] if ext == ".webm" else ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        acodec = ["-c:a", "libopus"] if ext == ".webm" else ["-c:a", "aac"]
        subprocess.check_call(
            [self.ff, "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=1",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
            + vcodec + acodec
            + ["-metadata", "comment=Made with AI - Higgsfield", "-metadata", "encoder=Adobe Firefly Video",
               "-metadata:s:v", "handler_name=Higgsfield generator", src]
        )
        if ext in (".mp4", ".mov"):
            # Append a C2PA-style top-level uuid box, as content-credential tools do.
            body = bytes.fromhex("d8fec3d61b0e483c92975828877ec481") + JUMBF
            with open(src, "ab") as f:
                f.write(struct.pack(">I", len(body) + 8) + b"uuid" + body)
            # And add rotation metadata to make sure it survives.
            rot = os.path.join(self.tmp, "rot" + ext)
            subprocess.check_call([self.ff, "-loglevel", "error", "-y", "-display_rotation", "90", "-i", src,
                                   "-c", "copy", "-map_metadata", "0", rot])
            # The remux drops our uuid box, so re-append it.
            with open(rot, "ab") as f:
                f.write(struct.pack(">I", len(body) + 8) + b"uuid" + body)
            src = rot
        return src

    def _run(self, ext):
        src = self._make(ext)
        before = core.scan(src)
        self.assertIsNone(before.error)
        self.assertTrue(before.ai_markers)
        dst = os.path.join(self.tmp, "cleaned", "out" + ext)
        after = core.clean(src, dst)
        self.assertEqual(after.ai_markers, [], after.metadata_blocks)
        raw = read(dst).lower()
        needles = [b"higgsfield", b"firefly", b"made with ai", b"c2pa"]
        if ext != ".webm":  # Matroska requires a WritingApp field; "Lavf" is not an AI tag
            needles.append(b"lavf")
        for needle in needles:
            self.assertNotIn(needle, raw)
        a, b = self._probe(src), self._probe(dst)
        self.assertEqual([s["codec_name"] for s in a["streams"]], [s["codec_name"] for s in b["streams"]])
        self.assertAlmostEqual(float(a["format"]["duration"]), float(b["format"]["duration"]), places=1)
        return a, b

    def test_mp4(self):
        a, b = self._run(".mp4")
        rot = lambda p: [sd.get("rotation") for sd in p["streams"][0].get("side_data_list", [])]
        self.assertEqual(rot(a), rot(b))
        self.assertTrue(rot(b))

    def test_mov(self):
        self._run(".mov")

    def test_webm(self):
        self._run(".webm")


if __name__ == "__main__":
    unittest.main()
