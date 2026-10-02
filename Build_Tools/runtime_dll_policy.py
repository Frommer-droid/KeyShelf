# -*- coding: utf-8 -*-
"""Fail-closed политика native runtime DLL для Windows/PyInstaller."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable

PYSIDE_MSVC_RUNTIME_NAMES = (
    "concrt140.dll",
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)


def build_trusted_binary_roots(
    project_root: str,
    extra_roots: Iterable[str] = (),
) -> tuple[str, ...]:
    candidates = (
        project_root,
        sys.prefix,
        sys.base_prefix,
        os.environ.get("SystemRoot", ""),
        *extra_roots,
    )
    return tuple(
        os.path.normcase(os.path.abspath(path))
        for path in candidates
        if path
    )


def prefer_pyside_msvc_runtime(
    binaries: Iterable[tuple[str, str, str]],
    pyside_dir: str,
) -> list[tuple[str, str, str]]:
    runtime_names = {name.casefold() for name in PYSIDE_MSVC_RUNTIME_NAMES}
    result = [
        entry
        for entry in binaries
        if os.path.basename(entry[0]).casefold() not in runtime_names
    ]
    for name in PYSIDE_MSVC_RUNTIME_NAMES:
        source_path = os.path.join(pyside_dir, name)
        if not os.path.isfile(source_path):
            raise FileNotFoundError(
                f"В установленном PySide6 отсутствует обязательная DLL: {source_path}"
            )
        result.append((name, source_path, "BINARY"))
    return result


def validate_trusted_binary_origins(
    binaries: Iterable[tuple[str, str, str]],
    trusted_roots: Iterable[str],
) -> None:
    normalized_roots = tuple(
        os.path.normcase(os.path.abspath(root)).rstrip("\\/")
        for root in trusted_roots
    )
    untrusted = []
    for destination, source, _typecode in binaries:
        normalized_source = os.path.normcase(os.path.abspath(source))
        if not any(
            normalized_source == root
            or normalized_source.startswith(root + os.sep)
            for root in normalized_roots
        ):
            untrusted.append((destination, source))
    if untrusted:
        details = "\n".join(
            f"  {destination} <- {source}" for destination, source in untrusted
        )
        raise RuntimeError(
            "PyInstaller обнаружил native-файлы из неразрешённых каталогов:\n"
            + details
        )
