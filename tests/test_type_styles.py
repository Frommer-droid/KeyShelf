import pytest
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QColor, QEnterEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionButton

from app.core.models import Account
from app.core.settings import Settings
from app.ui.cards import AccountCard
from app.ui.main_window import MainWindow
from app.ui.style_appendix import TYPE_BACKGROUNDS, TYPE_COLORS
from app.ui.theme import THEME_COLORS


@pytest.mark.parametrize("surface", ["filter", "card"])
def test_favorite_hover_fills_star_without_toggling(qtapp, tmp_path, surface):
    window = MainWindow(Settings(tmp_path / "settings.json"))
    card = AccountCard(Account(title="Synthetic", kind="api"),
                       lambda value: None, lambda a: None, lambda a: None, lambda a: None)
    window.vault_tab.cards_layout.insertWidget(0, card)
    window.vault_tab.setEnabled(True)
    button = window.vault_tab.favorites if surface == "filter" else card.favorite_button
    toggles = []
    button.toggled.connect(toggles.append)
    try:
        assert button.text() == "☆"
        QApplication.sendEvent(button, QEnterEvent(QPointF(), QPointF(), QPointF()))
        assert button.text() == "★" and not button.isChecked()
        assert toggles == []
        button.click()
        assert button.isChecked() and button.text() == "★"
        button.click()
        assert not button.isChecked() and button.text() == "★"
        QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
        assert button.text() == "☆" and not button.isChecked()
        assert toggles == [True, False]
        button.setChecked(True)
        QApplication.sendEvent(button, QEnterEvent(QPointF(), QPointF(), QPointF()))
        QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
        assert button.text() == "★" and button.isChecked()
    finally:
        window.exit_application()


@pytest.mark.parametrize("kind", ["api", "account", "other", "favorite"])
def test_filter_colors_stable_across_interaction(qtapp, tmp_path, kind):
    window = MainWindow(Settings(tmp_path / "settings.json"))
    window.vault_tab.setEnabled(True)
    window.show()
    qtapp.processEvents()
    button = {"api": window.vault_tab.filter_api, "account": window.vault_tab.filter_account, "other": window.vault_tab.filter_other,
              "favorite": window.vault_tab.favorites}[kind]
    try:
        for checked in (True, False):
            button.setChecked(checked)
            qtapp.processEvents()
            for extra in (QStyle.StateFlag.State_None, QStyle.StateFlag.State_MouseOver,
                          QStyle.StateFlag.State_Sunken | QStyle.StateFlag.State_MouseOver,
                          QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_MouseOver,
                          QStyle.StateFlag.State_None):
                option = QStyleOptionButton()
                option.initFrom(button)
                option.text = button.text()
                option.state = QStyle.StateFlag.State_Enabled | extra
                if checked:
                    option.state |= QStyle.StateFlag.State_On
                pixmap = QPixmap(button.size())
                pixmap.fill(QColor(THEME_COLORS["background"]))
                painter = QPainter(pixmap)
                button.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, button)
                painter.end()
                rendered = pixmap.toImage()
                highlighted = checked or extra & QStyle.StateFlag.State_MouseOver
                color = TYPE_COLORS[kind] if highlighted else THEME_COLORS["text_strong"]
                background = TYPE_BACKGROUNDS[kind] if highlighted else THEME_COLORS["surface_alt"]
                assert rendered.pixelColor(10, button.height() // 2) == QColor(background)
                border = rendered.pixelColor(0, button.height() // 2)
                if checked or extra & QStyle.StateFlag.State_MouseOver:
                    assert border == QColor(TYPE_COLORS[kind])
                else:
                    assert border != QColor(TYPE_COLORS[kind])
                assert button.isChecked() == checked
                # Check actual glyph pixels as well as background and outline.
                assert any(rendered.pixelColor(x, y) == QColor(color)
                           for x in range(13, button.width() - 13)
                           for y in range(7, button.height() - 7))
    finally:
        window.exit_application()


@pytest.mark.parametrize("favorite", [True, False])
@pytest.mark.parametrize("hover", [True, False])
def test_record_favorite_uses_global_favorite_style(qtapp, tmp_path, favorite, hover):
    window = MainWindow(Settings(tmp_path / "settings.json"))
    card = AccountCard(Account(title="Synthetic", kind="api", favorite=favorite),
                       lambda value: None, lambda a: None, lambda a: None, lambda a: None)
    window.vault_tab.cards_layout.insertWidget(0, card)
    window.vault_tab.setEnabled(True)
    window.show()
    qtapp.processEvents()
    try:
        button = card.favorite_button
        assert button.isChecked() == favorite
        assert button.objectName() == window.vault_tab.favorites.objectName()
        window.vault_tab.favorites.setChecked(favorite)
        qtapp.processEvents()
        samples = []
        for widget in (button, window.vault_tab.favorites):
            option = QStyleOptionButton()
            option.initFrom(widget)
            option.text = widget.text()
            option.state = QStyle.StateFlag.State_Enabled
            if hover:
                option.state |= QStyle.StateFlag.State_MouseOver
            if favorite:
                option.state |= QStyle.StateFlag.State_On
            pixmap = QPixmap(widget.size())
            pixmap.fill(QColor(THEME_COLORS["background"]))
            painter = QPainter(pixmap)
            widget.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, widget)
            painter.end()
            image = pixmap.toImage()
            highlighted = favorite or hover
            background = TYPE_BACKGROUNDS["favorite"] if highlighted else THEME_COLORS["surface_alt"]
            assert image.pixelColor(10, widget.height() // 2) == QColor(background)
            samples.append([image.pixelColor(x, widget.height() // 2) for x in (0, 4)])
        assert samples[0] == samples[1]
    finally:
        window.exit_application()
