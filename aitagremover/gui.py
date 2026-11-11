"""Desktop GUI (Tkinter - ships with Python on Windows and macOS)."""

import os
import queue
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, core

FILETYPES = [
    ("Images & videos", " ".join("*" + e for e in sorted(core.SUPPORTED_EXTS))),
    ("All files", "*.*"),
]


class App(object):
    def __init__(self, root):
        self.root = root
        root.title("Tag %s" % __version__)
        root.geometry("980x560")
        root.minsize(760, 420)

        self.files = []  # list of paths, index matches tree rows
        self.reports = {}
        self.out_dir = tk.StringVar(value="")
        self.status = tk.StringVar(value="Add images or videos to begin. Originals are never modified.")
        self.q = queue.Queue()
        self.busy = False

        top = ttk.Frame(root, padding=(10, 10, 10, 4))
        top.pack(fill="x")
        ttk.Button(top, text="Add files...", command=self.add_files).pack(side="left")
        ttk.Button(top, text="Add folder...", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(top, text="Clear list", command=self.clear).pack(side="left")
        self.clean_btn = ttk.Button(top, text="Clean all", command=self.clean_all)
        self.clean_btn.pack(side="right")

        outf = ttk.Frame(root, padding=(10, 0, 10, 6))
        outf.pack(fill="x")
        ttk.Label(outf, text="Save cleaned files to:").pack(side="left")
        ttk.Entry(outf, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(outf, text="Choose...", command=self.choose_out).pack(side="left")
        ttk.Label(outf, text="(blank = 'cleaned' folder next to each file)", foreground="#777").pack(side="left", padx=6)

        cols = ("type", "found", "status")
        mid = ttk.Frame(root, padding=(10, 0, 10, 0))
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=cols, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="File")
        self.tree.heading("type", text="Type")
        self.tree.heading("found", text="AI / provenance tags found")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=300)
        self.tree.column("type", width=60, anchor="center")
        self.tree.column("found", width=380)
        self.tree.column("status", width=200)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("ai", foreground="#b3261e")
        self.tree.tag_configure("ok", foreground="#1e7b34")
        self.tree.tag_configure("err", foreground="#8a6d00")
        self.tree.bind("<Double-1>", self.show_details)

        bottom = ttk.Frame(root, padding=10)
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status).pack(anchor="w", pady=(6, 0))
        ttk.Label(
            bottom,
            text="Note: removes metadata only. Invisible pixel watermarks (e.g. SynthID) are not metadata and are not affected.",
            foreground="#777",
        ).pack(anchor="w")

        if not core.find_ffmpeg():
            self.status.set("ffmpeg not found - images work, but videos need ffmpeg (see README).")

        root.after(100, self.poll)

    # ---- file list -------------------------------------------------------
    def add_files(self):
        paths = filedialog.askopenfilenames(title="Choose images or videos", filetypes=FILETYPES)
        self.add_paths(list(paths))

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder")
        if d:
            self.add_paths([d])

    def choose_out(self):
        d = filedialog.askdirectory(title="Output folder")
        if d:
            self.out_dir.set(d)

    def clear(self):
        if self.busy:
            return
        self.tree.delete(*self.tree.get_children())
        self.files = []
        self.reports = {}

    def add_paths(self, paths):
        new = [p for p in core.collect_files(paths) if p not in self.files]
        for p in new:
            self.files.append(p)
            self.tree.insert("", "end", iid=p, text=os.path.basename(p), values=("", "scanning...", ""))
        if new:
            self.run_bg(self._scan_worker, new)

    def _scan_worker(self, paths):
        for i, p in enumerate(paths):
            r = core.scan(p)
            self.q.put(("scanned", p, r))
            self.q.put(("progress", i + 1, len(paths)))
        self.q.put(("done", "Scanned %d file(s). Double-click a row for details." % len(paths)))

    # ---- cleaning --------------------------------------------------------
    def clean_all(self):
        if self.busy or not self.files:
            return
        out = self.out_dir.get().strip() or None
        self.run_bg(self._clean_worker, list(self.files), out)

    def _clean_worker(self, paths, out):
        ok = 0
        for i, p in enumerate(paths):
            out_dir = out or os.path.join(os.path.dirname(os.path.abspath(p)), "cleaned")
            dst = core.output_path_for(p, out_dir)
            try:
                if os.path.abspath(dst) == os.path.abspath(p):
                    raise ValueError("Output folder is the same as the source folder")
                after = core.clean(p, dst)
                if after.ai_markers:
                    self.q.put(("cleaned", p, "WARNING: still has " + ", ".join(after.ai_markers), "err"))
                else:
                    ok += 1
                    self.q.put(("cleaned", p, "Clean  ->  " + dst, "ok"))
            except Exception as e:
                self.q.put(("cleaned", p, "Failed: %s" % e, "err"))
            self.q.put(("progress", i + 1, len(paths)))
        self.q.put(("done", "Cleaned %d of %d file(s)." % (ok, len(paths))))
        if ok:
            self.q.put(("open", out or os.path.join(os.path.dirname(os.path.abspath(paths[0])), "cleaned")))

    # ---- threading plumbing ---------------------------------------------
    def run_bg(self, fn, *args):
        self.busy = True
        self.clean_btn.state(["disabled"])
        self.progress["value"] = 0
        self.status.set("Working...")
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "scanned":
                    _, p, r = msg
                    self.reports[p] = r
                    if r.error:
                        vals, tag = (r.kind, r.error, "Skipped"), "err"
                    elif r.ai_markers:
                        vals, tag = (r.kind, ", ".join(r.ai_markers), "Ready to clean"), "ai"
                    else:
                        found = "No AI tags (%d other metadata block(s))" % len(r.metadata_blocks)
                        vals, tag = (r.kind, found, "Ready to clean"), ""
                    if self.tree.exists(p):
                        self.tree.item(p, values=vals, tags=(tag,))
                elif kind == "cleaned":
                    _, p, text, tag = msg
                    if self.tree.exists(p):
                        v = list(self.tree.item(p, "values"))
                        v[2] = text
                        self.tree.item(p, values=v, tags=(tag,))
                elif kind == "progress":
                    _, i, n = msg
                    self.progress["maximum"] = n
                    self.progress["value"] = i
                elif kind == "done":
                    self.busy = False
                    self.clean_btn.state(["!disabled"])
                    self.status.set(msg[1])
                elif kind == "open":
                    open_folder(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def show_details(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.reports.get(sel[0])
        if not r:
            return
        text = "File: %s\nType: %s\n\n" % (r.path, r.kind)
        if r.error:
            text += "Error: " + r.error
        else:
            text += "Metadata blocks that will be removed:\n  " + ("\n  ".join(r.metadata_blocks) or "(none)")
            text += "\n\nAI / provenance markers:\n  " + ("\n  ".join(r.ai_markers) or "(none)")
        messagebox.showinfo("Details", text)


def open_folder(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if sys.platform == "win32":
            style.theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
