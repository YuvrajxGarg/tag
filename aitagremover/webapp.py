"""Tag's desktop UI: an HTML/CSS interface (aitagremover/ui) in a native window via pywebview.

Uses WebKit on macOS and Edge WebView2 on Windows, so both platforms get the same UI.
"""

import base64
import io
import json
import os
import subprocess
import sys
import threading

import webview
from webview.dom import DOMEventHandler

from . import __version__, core
from .settings import Settings
from .updater import Updater

UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    UI_DIR = os.path.join(sys._MEIPASS, "aitagremover", "ui")

BG = "#0b0b0c"


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def _thumb(path, kind):
    """Small JPEG data URL for the list, or None."""
    try:
        if kind in ("jpeg", "png", "webp"):
            from PIL import Image, ImageOps

            im = Image.open(path)
            im = ImageOps.exif_transpose(im)
            im.thumbnail((160, 160))
            if im.mode not in ("RGB", "L"):
                bg = Image.new("RGB", im.size, (23, 23, 26))
                im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[-1])
                im = bg
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=80)
            data = buf.getvalue()
        elif kind == "video":
            ff = core.find_ffmpeg()
            if not ff:
                return None
            kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
            data = subprocess.run(
                [ff, "-v", "error", "-ss", "0.5", "-i", path, "-frames:v", "1", "-vf", "scale=160:-2",
                 "-f", "image2pipe", "-c:v", "mjpeg", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, **kw).stdout
            if not data:
                return None
        else:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


class Api(object):
    def __init__(self):
        self._window = None
        self._items = {}  # id -> dict
        self._next_id = 1
        self._lock = threading.Lock()
        self._busy = False
        self._settings = Settings()
        self._updater = Updater(self._settings, lambda st: self._emit("update", st))

    # ---- helpers ---------------------------------------------------------
    def _emit(self, event, payload):
        if self._window:
            try:
                self._window.evaluate_js("window.App && App.on(%s, %s)" % (json.dumps(event), json.dumps(payload)))
            except Exception:
                pass

    def _public(self, it):
        r = it.get("report")
        return {
            "id": it["id"], "name": os.path.basename(it["path"]), "path": it["path"],
            "folder": os.path.dirname(it["path"]), "size": it["size"], "ext": os.path.splitext(it["path"])[1][1:].upper(),
            "kind": r.kind if r else None, "status": it["status"], "markers": r.ai_markers if r else [],
            "blocks": r.metadata_blocks if r else [], "error": it.get("error") or (r.error if r else None),
            "out": it.get("out"), "thumb": it.get("thumb"), "left": it.get("left", []),
        }

    # ---- called from JS --------------------------------------------------
    def info(self):
        return {"version": __version__, "ffmpeg": bool(core.find_ffmpeg()), "platform": sys.platform,
                "settings": self._settings.public(), "update": self._updater.state(),
                "home": os.path.expanduser("~")}

    # settings
    def set_setting(self, key, value):
        if key in ("out_mode", "custom_dir", "open_after", "auto_check", "auto_install", "welcomed"):
            self._settings.set(key, value)
            if key == "auto_install" and value and self._updater.phase == "available":
                threading.Thread(target=self._updater.stage_newest, daemon=True).start()
        return self._settings.public()

    # updates
    def check_updates(self):
        return self._updater.check(manual=True)

    def download_update(self):
        threading.Thread(target=self._updater.stage_newest, daemon=True).start()

    def install_update(self):
        def go():
            if self._updater.install() == "open_page":
                self.open_url(self._updater.state()["page"])
        threading.Thread(target=go, daemon=True).start()

    def open_url(self, url):
        if not (url.startswith("https://github.com/") or url.startswith("https://www.youtube.com/")):
            return
        import webbrowser
        webbrowser.open(url)

    def pick_files(self):
        exts = ";".join("*" + e for e in sorted(core.SUPPORTED_EXTS))
        res = self._window.create_file_dialog(
            webview.FileDialog.OPEN, allow_multiple=True,
            file_types=("Images and videos (%s)" % exts, "All files (*.*)"))
        if res:
            self.add_paths(list(res))

    def pick_folder(self):
        res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if res:
            self.add_paths([res[0] if isinstance(res, (list, tuple)) else res])

    def choose_output(self):
        res = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if res:
            return res[0] if isinstance(res, (list, tuple)) else res
        return None

    def add_paths(self, paths):
        files = core.collect_files(paths)
        known = {it["path"] for it in self._items.values()}
        new = []
        with self._lock:
            for p in files:
                if p in known:
                    continue
                known.add(p)
                it = {"id": self._next_id, "path": p, "size": _human(os.path.getsize(p)), "status": "scanning"}
                self._items[self._next_id] = it
                self._next_id += 1
                new.append(it)
        if not files:
            self._emit("toast", {"text": "No supported images or videos there", "err": True})
        for it in new:
            self._emit("upsert", self._public(it))
        if new:
            threading.Thread(target=self._scan, args=(new,), daemon=True).start()

    def _scan(self, items):
        for it in items:
            r = core.scan(it["path"])
            it["report"] = r
            it["status"] = "unsupported" if r.error else "ready"
            self._emit("upsert", self._public(it))
            if not r.error:
                it["thumb"] = _thumb(it["path"], r.kind)
                if it["thumb"]:
                    self._emit("upsert", self._public(it))

    def remove(self, item_id):
        with self._lock:
            self._items.pop(int(item_id), None)

    def clear(self):
        if not self._busy:
            with self._lock:
                self._items.clear()

    def clean(self, mode, custom_dir):
        if self._busy:
            return
        todo = [it for it in self._items.values() if it["status"] in ("ready", "failed", "warning")]
        if not todo:
            return
        self._busy = True
        threading.Thread(target=self._clean, args=(todo, mode, custom_dir), daemon=True).start()

    def _clean(self, todo, mode, custom_dir):
        ok = 0
        used = set()
        last_dir = None
        self._emit("busy", {"busy": True, "total": len(todo)})
        for i, it in enumerate(todo):
            src = it["path"]
            out_dir = custom_dir if (mode == "custom" and custom_dir) else os.path.join(os.path.dirname(src), "cleaned")
            dst = core.output_path_for(src, out_dir)
            stem, ext = os.path.splitext(dst)
            n = 1
            while dst in used:
                dst = "%s (%d)%s" % (stem, n, ext)
                n += 1
            used.add(dst)
            it["status"] = "cleaning"
            self._emit("upsert", self._public(it))
            try:
                if os.path.abspath(dst) == os.path.abspath(src):
                    raise ValueError("Output folder is the same as the source folder")
                after = core.clean(src, dst)
                it["out"] = dst
                it["left"] = after.ai_markers
                it["status"] = "warning" if after.ai_markers else "done"
                it["error"] = None
                ok += 0 if after.ai_markers else 1
                last_dir = os.path.dirname(dst)
            except Exception as e:
                it["status"] = "failed"
                it["error"] = str(e)
            self._emit("upsert", self._public(it))
            self._emit("progress", {"done": i + 1, "total": len(todo)})
        self._busy = False
        self._emit("busy", {"busy": False})
        self._emit("finished", {"ok": ok, "total": len(todo), "dir": last_dir})
        if ok and last_dir and self._settings.get("open_after"):
            self.reveal(last_dir)

    def reveal(self, path):
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
            elif os.name == "nt":
                if os.path.isfile(path):
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                else:
                    os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path) if os.path.isfile(path) else path])
        except Exception:
            pass


# ---- native window chrome -------------------------------------------------

def _style_mac(window):
    """Dark, transparent title bar with content running underneath (like Dwn)."""
    try:
        import AppKit
        from PyObjCTools import AppHelper

        def apply():
            w = window.native
            w.setStyleMask_(w.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView)
            w.setTitlebarAppearsTransparent_(True)
            w.setTitleVisibility_(AppKit.NSWindowTitleHidden)
            w.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameDarkAqua))
            w.setBackgroundColor_(AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(0.043, 0.043, 0.047, 1.0))
            w.setMovableByWindowBackground_(False)
            # pywebview paints the title bar strip with an opaque colour; make it see-through
            # so only the traffic lights float over the app (no grey bar covering the top).
            try:
                w.contentView().superview().subviews().lastObject().setBackgroundColor_(AppKit.NSColor.clearColor())
            except Exception:
                pass
            if hasattr(w, "setToolbarStyle_"):
                w.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)

        AppHelper.callAfter(apply)
    except Exception:
        pass


def _style_windows(window):
    """Dark title bar on Windows 10/11; caption colour matches the app on Windows 11."""
    try:
        import ctypes

        hwnd = window.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), 4) == 0:
                break
        caption = ctypes.c_int(0x000C0B0B)  # COLORREF 0x00BBGGRR for #0b0b0c
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def main():
    api = Api()
    # Only empty drag-region backgrounds move the window; buttons inside stay clickable.
    webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = True
    window = webview.create_window(
        "Tag", url=os.path.join(UI_DIR, "index.html"), js_api=api,
        width=1120, height=720, min_size=(880, 580), background_color=BG, easy_drag=False,
    )
    api._window = window

    def on_drop(e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            api.add_paths(paths)

    def on_loaded():
        try:
            window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass

    def quit_for_install():
        try:
            window.destroy()
        finally:
            t = threading.Timer(3.0, lambda: os._exit(0))
            t.daemon = True
            t.start()

    api._updater.on_quit_for_install = quit_for_install
    window.events.closing += lambda: api._updater.install_on_quit()
    window.events.loaded += lambda: api._updater.start()

    if sys.platform == "darwin":
        window.events.before_show += lambda: _style_mac(window)
    elif os.name == "nt":
        window.events.shown += lambda: _style_windows(window)
    window.events.loaded += on_loaded
    webview.start(debug=bool(os.environ.get("AITAG_DEBUG")))
    if os.name == "nt":
        # The window is closed. Leave without Python's normal shutdown: tearing down pythonnet and
        # WinForms there can crash, and a crash report keeps the process alive, which stalls the
        # update swap waiting for it to exit (the app then never reopened after an update).
        os._exit(0)


if __name__ == "__main__":
    main()
