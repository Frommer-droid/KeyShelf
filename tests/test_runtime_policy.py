from pathlib import Path

import pytest

from Build_Tools.runtime_dll_policy import (
    PYSIDE_MSVC_RUNTIME_NAMES,
    prefer_pyside_msvc_runtime,
    validate_trusted_binary_origins,
)


def test_native_origin_rejects_adjacent_prefix(tmp_path):
    trusted = tmp_path / "runtime"
    foreign = tmp_path / "runtime-foreign" / "native.dll"
    validate_trusted_binary_origins([("ok.dll", str(trusted / "ok.dll"), "BINARY")], [str(trusted)])
    with pytest.raises(RuntimeError, match="native.dll"):
        validate_trusted_binary_origins([("native.dll", str(foreign), "BINARY")], [str(trusted)])


def test_msvc_set_requires_every_member_and_replaces_old_runtime(tmp_path):
    for name in PYSIDE_MSVC_RUNTIME_NAMES[:-1]:
        (tmp_path / name).write_bytes(b"selected Qt runtime")
    old = [("vcruntime140.dll", str(tmp_path / "old.dll"), "BINARY")]
    with pytest.raises(FileNotFoundError):
        prefer_pyside_msvc_runtime(old, str(tmp_path))
    (tmp_path / PYSIDE_MSVC_RUNTIME_NAMES[-1]).write_bytes(b"selected Qt runtime")
    result = prefer_pyside_msvc_runtime(old, str(tmp_path))
    assert len(result) == len(PYSIDE_MSVC_RUNTIME_NAMES)
    assert all(Path(source).parent == tmp_path for _, source, _ in result)
