# PyInstaller build recipe for macOS (.app) and Windows (folder with .exe).
#   pyinstaller --noconfirm Tag.spec
import os
import sys

from PyInstaller.utils.hooks import collect_all

root = SPECPATH
version = open(os.path.join(root, "VERSION")).read().strip()

datas, binaries, hiddenimports = collect_all("imageio_ffmpeg")
datas += [
    (os.path.join(root, "aitagremover", "ui"), os.path.join("aitagremover", "ui")),
    (os.path.join(root, "VERSION"), "."),
]
hiddenimports += ["certifi"]

a = Analysis(
    [os.path.join(root, "Tag.py")],
    pathex=[root],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "_tkinter"] if sys.platform == "darwin" else [],
)
pyz = PYZ(a.pure)
icon = os.path.join(root, "assets", "AppIcon.icns" if sys.platform == "darwin" else "icon.ico")

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Tag",
    console=False,
    icon=icon,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Tag")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Tag.app",
        icon=icon,
        bundle_identifier="com.yuvrajgarg.tag",
        version=version,
        info_plist={
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            "CFBundleDisplayName": "Tag",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSRequiresAquaSystemAppearance": False,
        },
    )
