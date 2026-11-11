"""Core engine: detect and strip provenance / AI-generation metadata.

Images (JPEG, PNG, WebP) are cleaned losslessly by rewriting the container and
dropping metadata blocks -- pixel data is copied byte-for-byte, never re-encoded.
Videos are remuxed with ffmpeg using stream copy (no re-encode, no quality loss).

What is removed:
  * C2PA / Content Credentials manifests (JUMBF in JPEG APP11, PNG caBX,
    WebP C2PA chunk, MP4/MOV top-level uuid box)
  * XMP (incl. IPTC DigitalSourceType = trainedAlgorithmicMedia, Firefly,
    Photoshop history, CreatorTool, etc.)
  * EXIF (except image orientation, which is preserved), IPTC/Photoshop IRB,
    comments, text chunks, trailing data after end-of-image
  * Container-level and per-stream metadata tags, chapters, encoder tags in video

What is kept: pixel/audio/video data, ICC colour profiles, orientation/rotation,
transparency, animation, HDR/colour signalling.

What this CANNOT remove: invisible watermarks embedded in the pixels themselves
(e.g. Google SynthID, some model-specific watermarks). Those are not metadata.
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import zlib

# --------------------------------------------------------------------------
# Marker detection
# --------------------------------------------------------------------------

# (regex over lowercase bytes, human label). Order matters only for display.
AI_MARKERS = [
    (rb"c2pa", "C2PA Content Credentials"),
    (rb"jumb", "JUMBF manifest container"),
    (rb"contentauth|content credentials", "Content Authenticity Initiative"),
    (rb"trainedalgorithmicmedia", "IPTC: made with generative AI"),
    (rb"algorithmicmedia", "IPTC: algorithmic media"),
    (rb"digitalsourcetype", "IPTC DigitalSourceType tag"),
    (rb"firefly", "Adobe Firefly"),
    (rb"generative (fill|expand|extend|ai)", "Adobe Generative Fill/Expand"),
    (rb"higgsfield", "Higgsfield"),
    (rb"midjourney", "Midjourney"),
    (rb"dall[-\xb7 ]?e", "DALL-E"),
    (rb"openai", "OpenAI"),
    (rb"stable.?diffusion|comfyui|automatic1111", "Stable Diffusion"),
    (rb"runwayml|runway gen", "Runway"),
    (rb"kling", "Kling"),
    (rb"\bveo\b|imagen|gemini|google ai", "Google generative AI"),
    (rb"synthid", "SynthID reference"),
    (rb"made with ai|ai[- ]generated|ai info", "'Made with AI' label"),
]
_COMPILED = [(re.compile(p), label) for p, label in AI_MARKERS]


def find_markers(payload):
    """Return a sorted list of AI marker labels found in a bytes payload."""
    low = payload.lower()
    found = []
    for rx, label in _COMPILED:
        if rx.search(low) and label not in found:
            found.append(label)
    return found


class Block(object):
    """A chunk of a file. `keep` blocks are essential; others are metadata."""

    __slots__ = ("name", "raw", "keep", "scan")

    def __init__(self, name, raw, keep, scan=None):
        self.name = name
        self.raw = raw
        self.keep = keep
        self.scan = raw if scan is None else scan


class Report(object):
    def __init__(self, path, kind):
        self.path = path
        self.kind = kind
        self.metadata_blocks = []  # names of removable metadata blocks
        self.ai_markers = []  # labels
        self.error = None

    @property
    def has_ai_tags(self):
        return bool(self.ai_markers)

    def add_markers(self, labels):
        for lab in labels:
            if lab not in self.ai_markers:
                self.ai_markers.append(lab)


class UnsupportedFormat(Exception):
    pass


# --------------------------------------------------------------------------
# Format sniffing
# --------------------------------------------------------------------------

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_EXTS = VIDEO_EXTS | IMAGE_EXTS


def sniff(path):
    with open(path, "rb") as f:
        head = f.read(16)
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"uuid"):
        brand = head[8:12]
        if brand[:3] in (b"hei", b"mif", b"avi", b"hev"):
            return "heif"
        return "video"
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in (".heic", ".heif", ".avif"):
        return "heif"
    return "unknown"


# --------------------------------------------------------------------------
# JPEG
# --------------------------------------------------------------------------

def _jpeg_orientation(app1_payload):
    """Extract EXIF orientation (1-8) from an APP1 Exif payload, else None."""
    if not app1_payload.startswith(b"Exif\x00\x00"):
        return None
    t = app1_payload[6:]
    if len(t) < 8:
        return None
    endian = {b"II": "<", b"MM": ">"}.get(t[:2])
    if not endian:
        return None
    try:
        ifd = struct.unpack(endian + "I", t[4:8])[0]
        count = struct.unpack(endian + "H", t[ifd:ifd + 2])[0]
        for i in range(count):
            e = ifd + 2 + i * 12
            tag, typ, _cnt = struct.unpack(endian + "HHI", t[e:e + 8])
            if tag == 0x0112 and typ == 3:
                val = struct.unpack(endian + "H", t[e + 8:e + 10])[0]
                return val if 1 <= val <= 8 else None
    except (struct.error, IndexError):
        return None
    return None


def _minimal_exif(orientation):
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8)
    tiff += struct.pack(">H", 1)
    tiff += struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0)
    tiff += struct.pack(">I", 0)
    payload = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _jpeg_segment_name(marker, payload):
    if marker == 0xE1:
        if payload.startswith(b"Exif\x00"):
            return "EXIF"
        if payload.startswith(b"http://ns.adobe.com/xap/1.0/"):
            return "XMP"
        if payload.startswith(b"http://ns.adobe.com/xmp/extension/"):
            return "Extended XMP"
        return "APP1"
    if marker == 0xEB:
        return "C2PA/JUMBF (APP11)"
    if marker == 0xED:
        return "IPTC/Photoshop (APP13)"
    if marker == 0xE2:
        return "ICC profile" if payload.startswith(b"ICC_PROFILE\x00") else "APP2 (MPF/other)"
    if marker == 0xFE:
        return "Comment"
    return "APP%d" % (marker - 0xE0)


def _jpeg_blocks(data):
    if data[:2] != b"\xff\xd8":
        raise UnsupportedFormat("Not a JPEG")
    blocks = [Block("SOI", data[:2], True)]
    i = 2
    n = len(data)
    in_scan = False
    while i < n:
        if in_scan:
            # Copy entropy-coded data until a real marker appears.
            start = i
            while i < n - 1:
                if data[i] == 0xFF:
                    nxt = data[i + 1]
                    if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                        i += 2
                        continue
                    break
                i += 1
            else:
                i = n
            blocks.append(Block("scan data", data[start:i], True, scan=b""))
            in_scan = False
            continue
        if data[i] != 0xFF:
            # Garbage between segments: drop it.
            j = data.find(b"\xff", i)
            if j < 0:
                break
            i = j
            continue
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        seg_start = i - 1
        i += 1
        if marker == 0xD9:  # EOI
            blocks.append(Block("EOI", b"\xff\xd9", True))
            if i < n:
                blocks.append(Block("Trailing data after image", data[i:], False))
            return blocks
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            blocks.append(Block("RST", data[seg_start:i], True, scan=b""))
            continue
        if i + 2 > n:
            break
        length = struct.unpack(">H", data[i:i + 2])[0]
        seg_end = i + length
        raw = b"\xff" + bytes([marker]) + data[i:seg_end]
        payload = data[i + 2:seg_end]
        i = seg_end
        if 0xE0 <= marker <= 0xEF or marker == 0xFE:
            name = _jpeg_segment_name(marker, payload)
            keep = (
                (marker == 0xE0 and payload[:4] in (b"JFIF", b"JFXX"))
                or (marker == 0xE2 and payload.startswith(b"ICC_PROFILE\x00"))
                or (marker == 0xEE and payload.startswith(b"Adobe"))  # colour transform
            )
            blocks.append(Block(name, raw, keep, scan=b"" if keep else payload))
        else:
            blocks.append(Block("SOS" if marker == 0xDA else "marker", raw, True, scan=b""))
            if marker == 0xDA:
                in_scan = True
    blocks.append(Block("EOI", b"\xff\xd9", True))  # truncated file: close it
    return blocks


def _jpeg_strip(data, blocks):
    orientation = None
    for b in blocks:
        if b.name == "EXIF":
            orientation = _jpeg_orientation(b.raw[4:])
    kept = [b.raw for b in blocks if b.keep]
    if orientation and orientation != 1:
        # Re-insert a tiny EXIF holding only orientation, after SOI (+JFIF if present).
        pos = 2 if len(kept) > 1 and kept[1][:2] == b"\xff\xe0" else 1
        kept.insert(pos, _minimal_exif(orientation))
    return b"".join(kept)


# --------------------------------------------------------------------------
# PNG
# --------------------------------------------------------------------------

PNG_KEEP = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"cHRM", b"gAMA", b"iCCP",
    b"sBIT", b"sRGB", b"cICP", b"mDCv", b"cLLi", b"mDCV", b"cLLI", b"pHYs",
    b"bKGD", b"hIST", b"sPLT", b"acTL", b"fcTL", b"fdAT",
}


def _png_text_for_scan(ctype, data):
    try:
        if ctype == b"zTXt":
            k, rest = data.split(b"\x00", 1)
            return k + b" " + zlib.decompress(rest[1:])
        if ctype == b"iTXt":
            k, rest = data.split(b"\x00", 1)
            comp_flag = rest[0]
            rest = rest[2:]
            _lang, rest = rest.split(b"\x00", 1)
            _tk, text = rest.split(b"\x00", 1)
            return k + b" " + (zlib.decompress(text) if comp_flag else text)
    except Exception:
        pass
    return data


def _png_blocks(data):
    sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(sig):
        raise UnsupportedFormat("Not a PNG")
    blocks = [Block("signature", sig, True)]
    i = 8
    n = len(data)
    while i + 8 <= n:
        length = struct.unpack(">I", data[i:i + 4])[0]
        ctype = data[i + 4:i + 8]
        end = i + 12 + length
        raw = data[i:end]
        cdata = data[i + 8:i + 8 + length]
        keep = ctype in PNG_KEEP
        name = {
            b"caBX": "C2PA manifest (caBX)", b"eXIf": "EXIF", b"iTXt": "Text/XMP (iTXt)",
            b"tEXt": "Text (tEXt)", b"zTXt": "Text (zTXt)", b"tIME": "Timestamp",
        }.get(ctype, ctype.decode("latin-1"))
        blocks.append(Block(name, raw, keep, scan=b"" if keep else _png_text_for_scan(ctype, cdata)))
        i = end
        if ctype == b"IEND":
            if i < n:
                blocks.append(Block("Trailing data after image", data[i:], False))
            break
    return blocks


def _png_strip(data, blocks):
    return b"".join(b.raw for b in blocks if b.keep)


# --------------------------------------------------------------------------
# WebP
# --------------------------------------------------------------------------

WEBP_KEEP = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}


def _webp_blocks(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise UnsupportedFormat("Not a WebP")
    blocks = []
    i = 12
    riff_end = min(len(data), 8 + struct.unpack("<I", data[4:8])[0])
    while i + 8 <= riff_end:
        fourcc = data[i:i + 4]
        size = struct.unpack("<I", data[i + 4:i + 8])[0]
        end = i + 8 + size + (size & 1)
        raw = data[i:end]
        keep = fourcc in WEBP_KEEP
        name = {b"EXIF": "EXIF", b"XMP ": "XMP", b"C2PA": "C2PA manifest"}.get(
            fourcc, fourcc.decode("latin-1").strip())
        blocks.append(Block(name, raw, keep, scan=b"" if keep else raw[8:]))
        i = end
    if riff_end < len(data):
        blocks.append(Block("Trailing data after image", data[riff_end:], False))
    return blocks


def _webp_strip(data, blocks):
    body = []
    for b in blocks:
        if not b.keep:
            continue
        raw = b.raw
        if raw[:4] == b"VP8X":
            flags = raw[8] & ~(0x08 | 0x04)  # clear EXIF + XMP flags
            raw = raw[:8] + bytes([flags]) + raw[9:]
        body.append(raw)
    body = b"WEBP" + b"".join(body)
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --------------------------------------------------------------------------
# Video (ISO-BMFF scan + ffmpeg remux)
# --------------------------------------------------------------------------

_BMFF_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"udta", b"edts", b"dinf", b"ilst", b"meta", b"moof", b"traf"}
_BMFF_SKIP = {b"mdat", b"free", b"skip", b"stbl", b"wide"}


def _walk_bmff(f, start, end, path, out, depth=0):
    pos = start
    while pos + 8 <= end and depth < 12:
        f.seek(pos)
        hdr = f.read(8)
        if len(hdr) < 8:
            return
        size, typ = struct.unpack(">I4s", hdr)
        hlen = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            hlen = 16
        elif size == 0:
            size = end - pos
        if size < hlen:
            return
        name = typ.decode("latin-1")
        full = path + "/" + name if path else name
        body_start = pos + hlen
        body_end = min(pos + size, end)
        if typ in _BMFF_SKIP:
            pass
        elif typ in _BMFF_CONTAINERS:
            if typ == b"meta":
                f.seek(body_start)
                peek = f.read(8)
                # 'meta' is a FullBox in ISO files, a plain box in QuickTime.
                if peek[4:8] != b"hdlr":
                    body_start += 4
                out.append((full, b""))
            _walk_bmff(f, body_start, body_end, full, out, depth + 1)
        else:
            f.seek(body_start)
            payload = f.read(min(body_end - body_start, 8 * 1024 * 1024))
            if typ == b"uuid":
                full += " (" + payload[:16].hex() + ")"
            out.append((full, payload))
        pos = pos + size


def _scan_video(path, report):
    kind = None
    with open(path, "rb") as f:
        head = f.read(12)
        if head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"uuid"):
            kind = "bmff"
        if kind == "bmff":
            boxes = []
            _walk_bmff(f, 0, os.path.getsize(path), "", boxes)
            for name, payload in boxes:
                markers = find_markers(payload)
                interesting = (
                    markers
                    or name.startswith("uuid")
                    or "/udta/" in name or name.endswith("/udta")
                    or "/meta/" in name
                    or "XMP_" in name
                )
                if interesting:
                    report.metadata_blocks.append(name)
                report.add_markers(markers)
        else:
            # Matroska/WebM/AVI etc: tags live near start or end.
            size = os.path.getsize(path)
            chunk = 2 * 1024 * 1024
            f.seek(0)
            data = f.read(chunk)
            if size > chunk:
                f.seek(max(chunk, size - chunk))
                data += f.read(chunk)
            report.add_markers(find_markers(data))
            report.metadata_blocks.append("container tags")


def find_ffmpeg():
    """Locate an ffmpeg binary: env var, bundled copy, PATH, then imageio-ffmpeg."""
    env = os.environ.get("AITAG_FFMPEG")
    if env and os.path.isfile(env):
        return env
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(getattr(sys, "_MEIPASS", ""))
        bases.append(os.path.dirname(sys.executable))
    bases.append(os.path.dirname(os.path.abspath(__file__)))
    for base in bases:
        cand = os.path.join(base, exe)
        if base and os.path.isfile(cand):
            return cand
    found = shutil.which("ffmpeg")
    if found:
        return found
    for extra in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(extra):
            return extra
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _strip_video(src, dst):
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Install it (macOS: 'brew install ffmpeg', "
            "Windows: 'winget install ffmpeg') or 'pip install imageio-ffmpeg'."
        )
    ext = os.path.splitext(dst)[1].lower()
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", src,
        "-map", "0:V?", "-map", "0:a?",  # real video + audio; no cover art, data, subs
        "-c", "copy",
        "-map_metadata", "-1",
        "-map_metadata:s:v", "-1",
        "-map_metadata:s:a", "-1",
        "-map_chapters", "-1",
        "-fflags", "+bitexact",
        "-flags:v", "+bitexact",
        "-flags:a", "+bitexact",
    ]
    if ext in (".mp4", ".mov", ".m4v", ".3gp"):
        cmd += ["-movflags", "+faststart", "-write_tmcd", "0"]
    cmd.append(dst)
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    if proc.returncode != 0:
        if os.path.exists(dst):
            os.remove(dst)
        raise RuntimeError("ffmpeg failed: " + proc.stderr.decode("utf-8", "replace").strip()[-600:])


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_IMAGE_HANDLERS = {
    "jpeg": (_jpeg_blocks, _jpeg_strip),
    "png": (_png_blocks, _png_strip),
    "webp": (_webp_blocks, _webp_strip),
}


def scan(path):
    """Inspect a file and report which metadata/AI markers it carries."""
    kind = sniff(path)
    report = Report(path, kind)
    try:
        if kind in _IMAGE_HANDLERS:
            with open(path, "rb") as f:
                data = f.read()
            for b in _IMAGE_HANDLERS[kind][0](data):
                if not b.keep:
                    report.metadata_blocks.append(b.name)
                    report.add_markers(find_markers(b.scan))
        elif kind == "video":
            _scan_video(path, report)
        elif kind == "heif":
            raise UnsupportedFormat("HEIC/AVIF not supported yet - export as JPEG or PNG first")
        else:
            raise UnsupportedFormat("Unsupported file type")
    except Exception as e:  # report, don't crash the batch
        report.error = str(e)
    return report


def clean(src, dst):
    """Write a metadata-free copy of `src` to `dst`. Returns a post-clean Report."""
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ValueError("Refusing to overwrite the original file")
    kind = sniff(src)
    d = os.path.dirname(os.path.abspath(dst))
    if not os.path.isdir(d):
        os.makedirs(d)
    if kind in _IMAGE_HANDLERS:
        blocks_fn, strip_fn = _IMAGE_HANDLERS[kind]
        with open(src, "rb") as f:
            data = f.read()
        out = strip_fn(data, blocks_fn(data))
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, dst)
    elif kind == "video":
        _strip_video(src, dst)
    elif kind == "heif":
        raise UnsupportedFormat("HEIC/AVIF not supported yet - export as JPEG or PNG first")
    else:
        raise UnsupportedFormat("Unsupported file type")
    return scan(dst)


def output_path_for(src, out_dir):
    base = os.path.basename(src)
    return os.path.join(out_dir, base)


def collect_files(paths, recursive=True):
    """Expand files/folders into a list of supported media files."""
    result = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d != "cleaned" and not d.startswith(".")]
                for fn in sorted(files):
                    if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTS | {".heic", ".heif", ".avif"}:
                        result.append(os.path.join(root, fn))
                if not recursive:
                    break
        elif os.path.isfile(p):
            result.append(p)
    return result
