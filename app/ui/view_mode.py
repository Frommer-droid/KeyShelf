"""Режимы одного окна, отдельная геометрия и размер результатов поиска."""
from PySide6.QtCore import QEvent, QObject, QRect, Qt, QTimer
from PySide6.QtWidgets import QApplication

from app.ui.ui_scale_overrides import metrics


class ViewMode(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.mini = False
        self.switching = False
        self.fitting = False
        self.maxi_minimum = list(window.property("uiScaleBaseline")["min"])
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit)
        window.mini_panel.cards_page.installEventFilter(self)
        window.mini_panel.maxi_action.triggered.connect(lambda: self.set_mini(False))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.LayoutRequest:
            self.schedule_fit()
        return False

    def schedule_fit(self, *args):
        if self.mini and not self.window.exiting:
            self.fit_timer.start(0)

    def sync(self):
        wanted = self.window.settings.data["window_mode"] == "mini" and bool(self.window.vault)
        self.set_mini(wanted, remember=False)

    def set_mini(self, enabled, remember=True):
        window = self.window
        if enabled and (not window.vault or window.busy):
            return
        if remember:
            window.settings.data["window_mode"] = "mini" if enabled else "maxi"
            window.settings.save()
        if enabled == self.mini:
            return
        window.save_geometry()
        self.switching = True
        window.setUpdatesEnabled(False)
        try:
            old_search = window.mini_panel.search if self.mini else window.vault_tab.search
            new_search = window.mini_panel.search if enabled else window.vault_tab.search
            blocked = new_search.blockSignals(True)
            try:
                new_search.setText(old_search.text())
            finally:
                new_search.blockSignals(blocked)
            self.mini = enabled
            window.setWindowState(window.windowState() & ~(
                Qt.WindowState.WindowMaximized | Qt.WindowState.WindowMinimized))
            window.maxi_page.setVisible(not enabled)
            window.mini_panel.setVisible(enabled)
            baseline = window.property("uiScaleBaseline")
            baseline["min"] = [360, 72] if enabled else self.maxi_minimum
            window.setProperty("uiScaleBaseline", baseline)
            metrics(window, window.ui_scale.state.scale_factor)
            window.centralWidget().layout().activate()
            if enabled:
                data = window.settings.data
                rect = self.visible_rect(QRect(data["mini_pos_x"], data["mini_pos_y"],
                                               data["mini_width"], data["mini_height"]))
                window.setGeometry(rect)
            else:
                window.restore_geometry()
            window.refresh_cards()
            if enabled:
                self.fit()
            new_search.setFocus()
            new_search.selectAll()
        finally:
            window.geometry_timer.stop()
            window.setUpdatesEnabled(True)
            self.switching = False

    @staticmethod
    def visible_rect(rect):
        screens = QApplication.screens()
        screen = next((s for s in screens if s.availableGeometry().contains(rect.center())),
                      QApplication.primaryScreen())
        area = screen.availableGeometry()
        rect.setWidth(min(rect.width(), area.width()))
        rect.setHeight(min(rect.height(), area.height()))
        if not area.contains(rect):
            rect.moveCenter(area.center())
        return rect

    def fit(self):
        if not self.mini or self.window.exiting:
            return
        window = self.window
        panel = window.mini_panel
        self.fitting = True
        try:
            panel.cards_layout.activate()
            margins = panel.layout().contentsMargins()
            height = panel.search.sizeHint().height() + margins.top() + margins.bottom()
            if not panel.scroll.isHidden():
                height += panel.layout().spacing() + panel.cards_layout.sizeHint().height()
                height += panel.scroll.frameWidth() * 2
                height = min(height, window.settings.data["mini_height"])
            height = max(height, window.minimumSizeHint().height(), window.minimumHeight())
            current = window.geometry()
            rect = self.visible_rect(QRect(current.x(), current.y(), window.width(), height))
            window.setGeometry(rect)
        finally:
            self.fitting = False

    def resized(self):
        if self.mini and not self.switching and not self.fitting:
            if not self.window.mini_panel.scroll.isHidden():
                self.window.settings.data["mini_height"] = self.window.height()

    def save_geometry(self):
        window = self.window
        rect = window.normalGeometry() if window.isMaximized() else window.geometry()
        window.settings.data.update(mini_pos_x=rect.x(), mini_pos_y=rect.y(),
                                    mini_width=rect.width())
        window.settings.save()

    def stop(self):
        self.fit_timer.stop()
