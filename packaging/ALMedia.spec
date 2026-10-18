# -*- mode: python ; coding: utf-8 -*-
import ast
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo

project = Path(SPECPATH).parent
version = ast.literal_eval(ast.parse((project / "src/al_media/__init__.py").read_text(encoding="utf-8")).body[0].value)
version_parts = tuple(map(int, version.split("."))) + (0,)
version_resource = project / "build/version_info.txt"
version_resource.parent.mkdir(exist_ok=True)
version_resource.write_text(str(VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_parts, prodvers=version_parts, mask=0x3f,
                     flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("FileDescription", "AL Media"),
        StringStruct("ProductName", "AL Media"),
        StringStruct("Comments", "AnyLoad Media — video and audio downloader"),
        StringStruct("InternalName", "ALMedia"),
        StringStruct("FileVersion", version), StringStruct("ProductVersion", version),
        StringStruct("OriginalFilename", "ALMedia.exe")])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])])])), encoding="utf-8")
tools = project / "tools"
datas = [(str(tools / name), "tools") for name in ("yt-dlp.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe")]
datas += [(str(project / "THIRD_PARTY_NOTICES.md"), ".")]
datas += [(str(project / "LICENSE"), "."), (str(tools / "dependencies.json"), "tools")]
asset_names = ("app.ico", "app.png", "check.svg", "chevron-down.svg", "chevron-up.svg", "chevron-down-light.svg", "chevron-up-light.svg")
datas += [(str(project / "assets" / name), "assets") for name in asset_names]
for folder in ("icons", "sites"):
    datas += [(str(path), "assets/" + folder) for path in (project / "assets" / folder).glob("*.svg")]
if (tools / "licenses").exists():
    datas += [(str(path), "tools/licenses") for path in (tools / "licenses").iterdir() if path.is_file()]
a = Analysis([str(project / "main.py")], pathex=[str(project / "src")], binaries=[], datas=datas,
             hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
# Qt6Core imports the Windows ICU API from the OS. A build host may have an
# unrelated icuuc.dll on PATH (for example, from Poppler); PyInstaller can pick
# it up even though its exports are incompatible with Windows Qt.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {"icuuc.dll", "icudt78.dll"}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ALMedia", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          contents_directory="_runtime_v2",
          version=str(version_resource),
          manifest=str(project / "packaging/ALMedia.manifest"),
          icon=str(project / "assets" / "app.ico") if (project / "assets" / "app.ico").exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ALMedia")
