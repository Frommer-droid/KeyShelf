"""Audit native origins, prepare portable folder and legal/source bundle; never launch."""
import ast
import hashlib
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

from payload_policy import validate_payload
from runtime_dll_policy import (
    PYSIDE_MSVC_RUNTIME_NAMES,
    build_trusted_binary_roots,
    validate_trusted_binary_origins,
)

ROOT = Path(__file__).resolve().parents[1]


def is_license_file(item):
    path = Path(item)
    return ("__pycache__" not in path.parts and path.suffix.casefold() != ".pyc"
            and ("license" in str(path).lower() or "copying" in str(path).lower()))


def main():
    import PySide6

    source = ROOT / "Build_Tools/dist/KeyShelf"
    destination = ROOT / "KeyShelf"
    toc_path = ROOT / "Build_Tools/build/KeyShelf/COLLECT-00.toc"
    toc = ast.literal_eval(toc_path.read_text(encoding="utf-8"))
    entries = next(part for part in toc if isinstance(part, list))
    binaries = [entry for entry in entries if entry[2] in ("BINARY", "EXTENSION")]
    validate_trusted_binary_origins(binaries, build_trusted_binary_roots(str(ROOT)))
    pyside = Path(PySide6.__file__).parent
    for name in PYSIDE_MSVC_RUNTIME_NAMES:
        assert (source / "_internal" / name).read_bytes() == (pyside / name).read_bytes(), name
    if destination.exists():
        raise RuntimeError("Previous root build must be removed before PyInstaller")
    shutil.copytree(source, destination)
    documents = ["VERSION", "logo.ico", "LICENSE", "GPL-3.0.txt", "LGPL-3.0.txt", "THIRD_PARTY_NOTICES.md",
                 "SOURCE_CODE_ACCESS.md", "QT_PYSIDE6_COMPLIANCE.md", "EULA.md", "RELEASE_NOTES.md", "README.md", "README.en.md"]
    for name in documents:
        shutil.copy2(ROOT / name, destination / name)
    licenses = destination / "third-party-licenses"
    licenses.mkdir()
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        for item in dist.files or []:
            if is_license_file(item):
                actual = Path(dist.locate_file(item))
                if actual.is_file():
                    target = licenses / name / Path(item)
                    if not target.resolve().is_relative_to(licenses.resolve()):
                        raise RuntimeError("Unsafe license path in installed metadata")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(actual, target)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", licenses / "PYTHON-LICENSE.txt")
    sources = destination / "source"
    sources.mkdir()
    for folder in ["app", "Build_Tools", "tests", "tools"]:
        shutil.copytree(ROOT / folder, sources / folder,
                        ignore=shutil.ignore_patterns("__pycache__", "build", "dist", "installer-work"))
    for name in ["Acc-storage.py", "Запустить.cmd", "requirements.txt", "requirements-dev.txt", "requirements-build.txt",
                 "requirements-lock.txt", "pyproject.toml", ".gitignore", "DEVELOPER.md", "AGENT_HANDOFF.md", *documents]:
        shutil.copy2(ROOT / name, sources / name)
    (sources / "docs").mkdir()
    for name in ["app-icon.png", "vault-cards.png", "mini-mode.png", "import-export.md"]:
        shutil.copy2(ROOT / "docs" / name, sources / "docs" / name)
    manifest = {"version": (ROOT / "VERSION").read_text().strip(), "python": sys.version.split()[0],
                "native_origin_audit": "passed", "foreign_binary_origins": 0,
                "binary_count": len(binaries), "qt_msvc_set": list(PYSIDE_MSVC_RUNTIME_NAMES),
                "packages": {name: importlib.metadata.version(name) for name in ["PySide6", "pykeepass", "PyOTP", "pyinstaller"]}}
    (destination / "RUNTIME_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validate_payload(destination)
    audit = dict(manifest, binaries=[{"destination": item[0], "sha256": hashlib.sha256(Path(item[1]).read_bytes()).hexdigest()} for item in binaries])
    audit_folder = ROOT / ".verification"
    audit_folder.mkdir(exist_ok=True)
    (audit_folder / f"native-runtime-{manifest['version']}.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Native origins and Qt MSVC runtime verified; portable folder: {destination}")


if __name__ == "__main__":
    main()
