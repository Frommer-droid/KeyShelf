"""Reject user data and private development state before packaging a release."""

import sys
from pathlib import Path

RUNTIME_TEMPLATE = Path("_internal/pykeepass/blank_database.kdbx")
PRIVATE_DIRECTORIES = {".git", ".venv", ".verification", ".release-archive", "__pycache__"}


def validate_payload(folder: Path) -> int:
    folder = folder.resolve(strict=True)
    count = 0
    for item in folder.rglob("*"):
        relative = item.relative_to(folder)
        if item.is_symlink() or item.is_junction():
            raise ValueError(f"Linked item in release payload: {relative}")
        if PRIVATE_DIRECTORIES.intersection(relative.parts):
            raise ValueError(f"Private directory in release payload: {relative}")
        if not item.is_file():
            continue
        name = item.name.casefold()
        if name == "settings.json" or name.endswith((".log", ".pyc")):
            raise ValueError(f"User/runtime state in release payload: {relative}")
        if (name.endswith(".kdbx") or ".kdbx." in name) and relative != RUNTIME_TEMPLATE:
            raise ValueError(f"User vault in release payload: {relative}")
        count += 1
    return count


if __name__ == "__main__":
    print(f"Release payload verified: {validate_payload(Path(sys.argv[1]))} files")
