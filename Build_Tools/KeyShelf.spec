import os
import sys
from pathlib import Path

import PySide6
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "Build_Tools"))
from runtime_dll_policy import build_trusted_binary_roots, prefer_pyside_msvc_runtime, validate_trusted_binary_origins

pyside = Path(PySide6.__file__).parent
os.environ["PATH"] = os.pathsep.join(str(p) for p in [pyside, pyside.parent / "shiboken6", Path(sys.executable).parent,
                                                    Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
                                                    Path(os.environ["SystemRoot"]) / "System32"])
translation = pyside / "translations/qtbase_ru.qm"
if not translation.is_file():
    raise RuntimeError("Russian Qt translation missing")
datas = [(str(ROOT / "logo.ico"), "."), (str(ROOT / "VERSION"), "."),
         (str(translation), "PySide6/translations")]
datas += collect_data_files("pykeepass")
a = Analysis([str(ROOT / "Acc-storage.py")], pathex=[str(ROOT)],
             datas=datas, binaries=collect_dynamic_libs("Cryptodome"),
             hiddenimports=collect_submodules("Cryptodome", filter=lambda name: not name.startswith("Cryptodome.SelfTest")),
             excludes=["tkinter", "pytest", "ruff", "PySide6.QtQuick", "PySide6.QtQml"],
             noarchive=False)
roots = build_trusted_binary_roots(str(ROOT))
validate_trusted_binary_origins(a.binaries, roots)
a.binaries = prefer_pyside_msvc_runtime(a.binaries, str(pyside))
validate_trusted_binary_origins(a.binaries, roots)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="KeyShelf", console=False,
          icon=str(ROOT / "logo.ico"), version=str(ROOT / "Build_Tools/version_info.txt"), upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="KeyShelf", upx=False)
