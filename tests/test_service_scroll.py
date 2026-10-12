"""Service refresh keeps the user's place after deletion."""

import pytest

from app.core.models import Service
from tests.test_mini_mode import settle
from tests.test_ui import make_window


@pytest.mark.parametrize("index,filtered", [(45, False), (89, False), (45, True)])
def test_deleted_service_selects_visible_neighbor_and_keeps_scroll(qtapp, tmp_path, index, filtered):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.services = [Service(str(i), f"{i:03} {'Match' if i % 2 else 'Other'}")
                                    for i in reversed(range(90))]
        window.snapshot.accounts = []
        window.refresh_services()
        tab = window.vault_tab
        if filtered:
            tab.service_search.setText("Match")
        widget = tab.services
        widget.setCurrentRow(index)
        widget.scrollToItem(widget.currentItem())
        settle(qtapp)
        scrollbar = widget.verticalScrollBar()
        before = scrollbar.value()
        assert before > 0
        window.snapshot.services = [s for s in window.snapshot.services if s.id != str(index)]
        window.refresh_services()
        settle(qtapp)
        expected = index + (2 if filtered else 1) if index < 89 else 88
        assert window.current_service() == str(expected)
        assert not widget.currentItem().isHidden()
        assert scrollbar.value() == min(before, scrollbar.maximum())
        assert tab.service_search.text() == ("Match" if filtered else "")
    finally:
        window.exit_application()


def test_refresh_keeps_selection_and_scroll_then_handles_empty_list(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.services = [Service(str(i), f"Service {i:03}") for i in range(90)]
        window.snapshot.accounts = []
        window.refresh_services()
        widget = window.vault_tab.services
        widget.setCurrentRow(45)
        settle(qtapp)
        widget.scrollToItem(widget.item(40))
        settle(qtapp)
        before = widget.verticalScrollBar().value()
        assert before > 0
        window.refresh_services()
        settle(qtapp)
        assert window.current_service() == "45"
        assert widget.verticalScrollBar().value() == before
        window.snapshot.services = []
        window.refresh_services()
        settle(qtapp)
        assert window.current_service() is None
        assert widget.count() == 0
        assert widget.verticalScrollBar().value() == 0
    finally:
        window.exit_application()


def test_deleted_only_matching_service_does_not_select_hidden_item(qtapp, tmp_path):
    window = make_window(qtapp, tmp_path)
    try:
        window.snapshot.services = [Service("a", "Match"), Service("b", "Other")]
        window.snapshot.accounts = []
        window.refresh_services()
        window.vault_tab.service_search.setText("Match")
        window.snapshot.services = [Service("b", "Other")]
        window.refresh_services()
        settle(qtapp)
        assert window.current_service() is None
        assert window.vault_tab.all_services.isChecked()
        assert window.vault_tab.services.item(0).isHidden()
        assert not window.vault_tab.service_empty.isHidden()
    finally:
        window.exit_application()
