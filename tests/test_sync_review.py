import base64
import hashlib
import io

import pytest

from app.services.sync_review import SyncReview
from app.services.vault import Vault, VaultError


@pytest.fixture
def proposal(tmp_path):
    vault, _ = Vault.create(tmp_path / "base.kdbx", "synthetic-master-123")
    original = vault.path.read_bytes()
    kp = Vault.decode(original, vault.password)
    group = kp.add_group(kp.root_group, "Phone group")
    kp.add_entry(group, "Phone record", "synthetic-login", "synthetic-secret")
    buffer = io.BytesIO()
    kp.save(buffer)
    incoming = buffer.getvalue()
    review = SyncReview(tmp_path / "reviews", vault)
    review.offer(incoming, vault.digest.hex(), modified=1791790000000)
    yield vault, original, incoming, review
    vault.close()


def test_stage_survives_recreation_without_replacing(proposal):
    vault, original, incoming, review = proposal
    restored = SyncReview(review.root.parent, vault)
    restored.offer(incoming, vault.digest.hex(), modified=1791790000000)
    assert restored.state["modified"] == 1791790000000
    assert vault.path.read_bytes() == original
    assert not vault.path.with_suffix(".kdbx.bak").exists()
    assert (
        restored.root / (hashlib.sha256(incoming).hexdigest() + ".kdbx")
    ).read_bytes() == incoming
    assert b"synthetic-secret" not in restored.path.read_bytes()


def test_accept_mirrors_and_preserves_both_versions(proposal):
    vault, original, incoming, review = proposal
    result = review.apply()
    assert result.accounts[0].title == "Phone record"
    assert vault.path.read_bytes() == incoming
    assert vault.path.with_suffix(".kdbx.bak").read_bytes() == original
    for raw in (original, incoming):
        assert (review.root / (hashlib.sha256(raw).hexdigest() + ".kdbx")).read_bytes() == raw


def test_reject_preserves_computer_and_requests_phone_restoration(proposal):
    vault, original, incoming, review = proposal
    review.reject_phone()
    restored = SyncReview(review.root.parent, vault)
    assert restored.state["decision"] == "restore_phone"
    assert restored.active and vault.path.read_bytes() == original
    assert len(list(restored.root.glob("*.kdbx"))) == 2


def test_stale_confirmation_never_overwrites_local_edits(proposal):
    vault, original, incoming, review = proposal
    vault.service("New local change")
    changed = vault.path.read_bytes()
    with pytest.raises(VaultError, match="изменилась"):
        review.apply()
    with pytest.raises(VaultError, match="изменилась"):
        review.reject_phone()
    assert vault.path.read_bytes() == changed
    assert not review.active


def test_new_offer_invalidates_old_rejection(proposal):
    vault, original, incoming, review = proposal
    review.reject_phone()
    kp = Vault.decode(incoming, vault.password)
    kp.add_group(kp.root_group, "Another change")
    buffer = io.BytesIO()
    kp.save(buffer)
    review.offer(buffer.getvalue(), vault.digest.hex())
    assert not review.state["decision"]


def test_invalid_offer_and_corrupted_proposal_leave_base_unchanged(proposal):
    vault, original, incoming, review = proposal
    with pytest.raises(VaultError):
        review.offer(b"invalid", vault.digest.hex())
    (review.root / (review.state["remote"] + ".kdbx")).write_bytes(b"corrupted")
    with pytest.raises(VaultError, match="повреждена"):
        review.apply()
    assert vault.path.read_bytes() == original


@pytest.fixture
def ui_proposal(qtapp, tmp_path, monkeypatch):
    import app.ui.wifi_sync as module
    from app.core.settings import Settings
    from app.ui.main_window import MainWindow

    monkeypatch.setattr(module, "ROOT", tmp_path)
    window = MainWindow(Settings(tmp_path / "settings.json"))
    vault, state = Vault.create(tmp_path / "ui.kdbx", "synthetic-master-123")
    window.opened((vault, state))
    original = vault.path.read_bytes()
    kp = Vault.decode(original, vault.password)
    kp.add_group(kp.root_group, "Mobile")
    buffer = io.BytesIO()
    kp.save(buffer)
    raw = buffer.getvalue()

    class FakeServer:
        def notify(self):
            pass

        def close(self):
            pass

    window.wifi_sync.server = FakeServer()
    body = {
        "protocol": 3,
        "expected": vault.digest.hex(),
        "modified": 1791790000000,
        "blob": base64.b64encode(raw).decode(),
    }
    yield window, original, raw, body
    window.exit_application()


def test_qt_only_two_answers_and_reject_restores_phone(ui_proposal, qtapp, tmp_path):
    from app.ui.wifi_sync import Request

    window, original, raw, body = ui_proposal
    sync = window.wifi_sync
    sync.handle(Request("/upload", body))
    dialog = sync.review_dialog
    assert {button.text() for button in dialog.buttons()} == {"Принять", "Отклонить"}
    assert "База телефона изменена:" in dialog.text()
    qtapp.processEvents()
    assert dialog.grab().save(str(tmp_path / "windows-sync-dialog.png"))
    next(button for button in dialog.buttons() if button.text() == "Отклонить").click()
    assert window.vault.path.read_bytes() == original
    poll = Request(
        "/sync",
        {
            "protocol": 3,
            "base": window.vault.digest.hex(),
            "outgoing": hashlib.sha256(raw).hexdigest(),
            "hash": hashlib.sha256(raw).hexdigest(),
        },
    )
    sync.handle(poll)
    status, result = poll.response
    assert status == 200 and result["action"] == "restore"
    assert result["expectedLocal"] == hashlib.sha256(raw).hexdigest()
    assert base64.b64decode(result["blob"]) == original
    # A newer phone version must never be restored by the old rejection.
    poll = Request(
        "/sync",
        {"protocol": 3, "base": window.vault.digest.hex(), "outgoing": "a" * 64, "hash": "a" * 64},
    )
    sync.handle(poll)
    assert poll.response[1]["action"] == "push"
    # Completing the restore must consume the rejection, not reject future edits.
    completed = Request(
        "/sync",
        {"protocol": 3, "base": window.vault.digest.hex(), "hash": window.vault.digest.hex()},
    )
    sync.handle(completed)
    assert completed.response[1]["action"] == "idle"
    assert sync.review.state == {}
    repeat = Request(
        "/sync",
        {
            "protocol": 3,
            "base": window.vault.digest.hex(),
            "outgoing": hashlib.sha256(raw).hexdigest(),
            "hash": hashlib.sha256(raw).hexdigest(),
        },
    )
    sync.handle(repeat)
    assert repeat.response[1]["action"] == "push"


def test_qt_phone_rejection_restores_desktop_without_second_prompt(ui_proposal, qtapp):
    from app.ui.wifi_sync import Request
    from tests.test_ui import process

    window, original, raw, body = ui_proposal
    request = Request("/upload", dict(body, decision="restore_desktop"))
    window.wifi_sync.handle(request)
    process(qtapp, lambda: request.ready.is_set(), timeout=15)
    assert request.response == (
        200,
        {
            "protocol": 3,
            "action": "same",
            "hash": hashlib.sha256(raw).hexdigest(),
        },
    )
    assert window.vault.path.read_bytes() == raw
    assert window.vault.path.with_suffix(".kdbx.bak").read_bytes() == original
    assert window.wifi_sync.review_dialog is None


def test_qt_legacy_and_stale_phone_rejection_are_rejected(ui_proposal):
    from app.ui.wifi_sync import Request

    window, original, raw, body = ui_proposal
    sync = window.wifi_sync
    request = Request("/upload", dict(body, protocol=1))
    sync.handle(request)
    assert request.response[0] == 426
    changed = window.vault.service("Changed after prompt")
    window.snapshot = changed
    current = window.vault.path.read_bytes()
    request = Request("/upload", dict(body, decision="restore_desktop"))
    sync.handle(request)
    assert request.response[0] == 409 and window.vault.path.read_bytes() == current


def test_accepting_phone_deletion_removes_record_from_computer(proposal):
    vault, original, incoming, review = proposal
    review.apply()  # The computer now has the record originally sent by the phone.
    with_record = vault.path.read_bytes()
    kp = Vault.decode(with_record, vault.password)
    kp.delete_entry(kp.entries[0])
    buffer = io.BytesIO()
    kp.save(buffer)
    deleted = buffer.getvalue()
    review.offer(deleted, vault.digest.hex(), modified=1791790000000)
    assert vault.path.read_bytes() == with_record
    result = review.apply()
    assert result.accounts == []
    assert vault.path.read_bytes() == deleted
    assert vault.path.with_suffix(".kdbx.bak").read_bytes() == with_record


def test_computer_acceptance_checks_current_phone_version_before_apply(ui_proposal):
    from app.ui.wifi_sync import Request

    window, original, raw, body = ui_proposal
    sync = window.wifi_sync
    sync.handle(Request("/upload", body))
    next(button for button in sync.review_dialog.buttons() if button.text() == "Принять").click()
    assert sync.review.state["decision"] == "accept_phone"
    assert window.vault.path.read_bytes() == original
    # Source edits made after the dialog cannot be replaced by the old accepted snapshot.
    poll = Request(
        "/sync",
        {"protocol": 3, "base": window.vault.digest.hex(), "outgoing": "a" * 64, "hash": "a" * 64},
    )
    sync.handle(poll)
    assert poll.response[1]["action"] == "push"
    assert window.vault.path.read_bytes() == original
