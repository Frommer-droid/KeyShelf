import json

import pytest

from app.core.settings import ROOT, Settings, validate_vault_path


def test_settings_malformed_and_whitelist(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("invalid", encoding="utf-8")
    settings = Settings(path)
    assert settings.data["recent_vaults"] == []
    path.write_text(json.dumps(dict(idle_minutes=-20, splitter=["bad"], password="synthetic-only")), encoding="utf-8")
    settings = Settings(path)
    assert "idle_minutes" not in settings.data
    assert settings.data["splitter"] == [240, 840]
    settings.save()
    assert "password" not in path.read_text()


def test_no_vault_in_source_tree(tmp_path):
    with pytest.raises(ValueError, match="вне"):
        validate_vault_path(ROOT / "test.kdbx")
    assert validate_vault_path(tmp_path / "test.kdbx") == tmp_path / "test.kdbx"
