from pathlib import Path

import pytest

from Build_Tools.payload_policy import validate_payload

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_template_is_retained(tmp_path):
    template = tmp_path / "_internal/pykeepass/blank_database.kdbx"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"synthetic-runtime-template")
    (tmp_path / "KeyShelf.exe").write_bytes(b"synthetic-exe")
    assert validate_payload(tmp_path) == 2


@pytest.mark.parametrize("name", [
    "settings.json", "startup.log", "private.kdbx", "private.kdbx.bak",
    "source/settings.json", "_internal/unexpected.kdbx", "source/app/__pycache__/module.pyc",
    "source/.git/config", "source/.verification/report.json",
])
def test_user_and_private_files_block_packaging(tmp_path, name):
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"synthetic-only")
    with pytest.raises(ValueError):
        validate_payload(tmp_path)


def test_installer_preserves_user_files_without_dropping_runtime_template():
    script = (ROOT / "Build_Tools/installer.iss").read_text(encoding="utf-8-sig")
    assert "[UninstallDelete]" not in script
    files = script.split("[Files]", 1)[1].split("[Icons]", 1)[0]
    patterns = files.split('Excludes: "', 1)[1].split('"', 1)[0].split(",")
    assert {r"\settings.json", r"\*.log", r"\*.kdbx", r"\*.kdbx.*"} <= set(patterns)
    # Inno patterns without a leading slash match at every directory depth.
    assert "*.kdbx" not in patterns
