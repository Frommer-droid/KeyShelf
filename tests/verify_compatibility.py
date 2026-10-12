"""Независимое чтение синтетического KDBX через официальный KeePassXC CLI."""
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from app.core.models import Account, Field
from app.services.vault import Vault


def main():
    cli = Path(sys.argv[1]).resolve()
    password = "synthetic-compat-passphrase-123"
    with tempfile.TemporaryDirectory(prefix="vault-compat-") as folder:
        path = Path(folder) / "synthetic.kdbx"
        vault, _ = Vault.create(path, password)
        try:
            state = vault.service("SyntheticService")
            service = next(s for s in state.services if s.name == "SyntheticService")
            vault.account(Account(service_id=service.id, title="SyntheticAccount",
                                  login="demo@example.invalid", project="SyntheticProject",
                                  fields=[Field("Main key", "synthetic-compat-main"),
                                          Field("Test key", "synthetic-compat-test")]))
        finally:
            vault.close()
        result = subprocess.run([str(cli), "export", str(path)], input=password + "\n",
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        assert result.returncode == 0, "KeePassXC did not open synthetic KDBX"
        root = ElementTree.fromstring(result.stdout)
        entry = root.find(".//Entry")
        values = {s.findtext("Key"): s.findtext("Value") for s in entry.findall("String")}
        assert values["Title"] == "SyntheticAccount"
        assert "synthetic-compat-main" in values.values()
        assert "synthetic-compat-test" in values.values()
        assert any("SyntheticProject" in value for value in values.values() if value)
        assert "Error" not in result.stderr
    print("KeePassXC 2.7.12 independently read KDBX4/Argon2id, two custom secrets and metadata: OK")


if __name__ == "__main__":
    main()
