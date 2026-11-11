"""Command-line interface.

    python -m aitagremover scan  <files/folders...>
    python -m aitagremover clean <files/folders...> [-o OUTPUT_DIR]
"""

import argparse
import os
import sys

from . import core


def _fmt(report):
    if report.error:
        return "  ! " + report.error
    lines = []
    lines.append("  metadata blocks: " + (", ".join(report.metadata_blocks) or "none"))
    lines.append("  AI markers:      " + (", ".join(report.ai_markers) or "none"))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="tag", description="Detect and remove AI / C2PA metadata from images and videos.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="report metadata without changing anything")
    s.add_argument("paths", nargs="+")
    c = sub.add_parser("clean", help="write cleaned copies (originals are never modified)")
    c.add_argument("paths", nargs="+")
    c.add_argument("-o", "--output", help="output folder (default: a 'cleaned' folder next to each file)")
    args = p.parse_args(argv)
    if not args.cmd:
        p.print_help()
        return 1

    files = core.collect_files(args.paths)
    if not files:
        print("No supported files found.")
        return 1

    failures = 0
    for path in files:
        print(path)
        if args.cmd == "scan":
            r = core.scan(path)
            print(_fmt(r))
            failures += bool(r.error)
            continue
        out_dir = args.output or os.path.join(os.path.dirname(os.path.abspath(path)), "cleaned")
        dst = core.output_path_for(path, out_dir)
        before = core.scan(path)
        if before.error:
            print("  ! skipped: " + before.error)
            failures += 1
            continue
        try:
            after = core.clean(path, dst)
        except Exception as e:
            print("  ! failed: %s" % e)
            failures += 1
            continue
        print("  removed: " + (", ".join(before.metadata_blocks) or "nothing to remove"))
        if before.ai_markers:
            print("  AI tags removed: " + ", ".join(before.ai_markers))
        if after.ai_markers:
            print("  ! still present: " + ", ".join(after.ai_markers))
            failures += 1
        print("  -> " + dst)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
