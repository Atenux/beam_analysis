"""build_exe.py -- Build a standalone executable using PyInstaller."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig


_RUNTIME_HOOK = """\
import os, sys
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
    for _name in os.listdir(_base):
        if _name.endswith('.libs') and os.path.isdir(os.path.join(_base, _name)):
            os.add_dll_directory(os.path.join(_base, _name))
    _ps = os.path.join(_base, 'PySide6')
    if os.path.isdir(_ps):
        os.add_dll_directory(_ps)
"""


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base_dir, "dist")
    build_dir = os.path.join(base_dir, "build")

    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    for f in os.listdir(base_dir):
        if f.endswith(".spec"):
            os.remove(os.path.join(base_dir, f))

    entry_point = os.path.join(base_dir, "beam_analyzer", "main.py")
    sp = sysconfig.get_path("purelib")

    hook_file = os.path.join(base_dir, "_pyi_rthook.py")
    with open(hook_file, "w") as fh:
        fh.write(_RUNTIME_HOOK)

    cadquery_libs = os.path.join(sp, "cadquery_ocp.libs")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "BeamAnalyzer",
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        # DLL search paths must be set before any native import
        "--runtime-hook", hook_file,
        # OCP: include every submodule stub + the compiled .pyd
        "--collect-all", "OCP",
        # cadquery_ocp_proxy is imported transitively
        "--hidden-import", "cadquery_ocp_proxy",
        # OCCT native shared libraries (delvewheel .libs directory)
        "--add-data", f"{cadquery_libs}{os.pathsep}cadquery_ocp.libs",
        # Shapely, matplotlib, and other hidden imports
        "--hidden-import", "shapely",
        "--hidden-import", "shapely.geometry",
        "--hidden-import", "shapely.ops",
        "--hidden-import", "shapely.validation",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "--hidden-import", "matplotlib.backends.backend_qt",
        entry_point,
    ]

    print("Running PyInstaller ...")
    for c in cmd:
        print(f"  {c}")
    subprocess.run(cmd, check=True)

    if os.path.exists(hook_file):
        os.remove(hook_file)

    out_dir = os.path.join(dist_dir, "BeamAnalyzer")
    print(f"\nBuild complete! Executable is in: {out_dir}")
    print(f"Run: {os.path.join(out_dir, 'BeamAnalyzer.exe')}")


if __name__ == "__main__":
    main()
