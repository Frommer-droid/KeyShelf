"""Whole-UI scaling and screen hooks, with explicit window resize policy."""
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QWidget
from shiboken6 import isValid

from app.services.ui_scale import resolve_screen, target_window_size
from app.ui.style_appendix import appendix
from app.ui.theme import apply_theme
from app.ui.ui_scale_overrides import metrics


class UIScaleRuntime(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.application = QApplication.instance()
        self.state = None
        self.screen = None
        self.handle = None
        self.applying = False
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update_children)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.setSingleShot(True)
        self.metrics_timer.timeout.connect(self.screen_update)
        combo = window.system_tab.scale_combo
        combo.setCurrentIndex(combo.findData(window.settings.data["ui_scale_delta_percent"]))
        combo.currentIndexChanged.connect(self.manual_change)
        for signal in (self.application.primaryScreenChanged, self.application.screenAdded,
                       self.application.screenRemoved):
            signal.connect(self.schedule_screen_update)
        self.application.installEventFilter(self)
        metrics(window, 1.0, capture_only=True)
        self.apply("startup")

    def eventFilter(self, watched, event):
        if self.stopped or self.applying or not isinstance(watched, QWidget):
            return False
        owner = watched
        while owner is not None and owner is not self.window:
            owner = owner.parentWidget()
        if owner is self.window:
            if event.type() == QEvent.Type.ChildAdded:
                self.timer.start(0)
            elif event.type() == QEvent.Type.Show:
                if watched is self.window:
                    self.install_window_hook()
                elif isinstance(watched, QDialog):
                    self.applying = True
                    try:
                        metrics(watched, self.state.scale_factor)
                        if not watched.property("uiScaleInitialSizeApplied"):
                            screen = watched.screen() or self.screen
                            if screen is not None:
                                area = screen.availableGeometry()
                                hint = watched.minimumSizeHint().expandedTo(watched.minimumSize())
                                watched.resize(*target_window_size(
                                    watched.width(), watched.height(), self.state.scale_factor,
                                    hint.width(), hint.height(), area.width(), area.height()))
                            watched.setProperty("uiScaleInitialSizeApplied", True)
                    finally:
                        self.applying = False
                self.timer.start(0)
        return False

    def install_window_hook(self):
        handle = self.window.windowHandle()
        if handle is not None and handle is not self.handle:
            self.handle = handle
            handle.screenChanged.connect(self.schedule_screen_update)
            self.schedule_screen_update()

    def schedule_screen_update(self, *args):
        if not self.stopped:
            self.metrics_timer.start(50)

    def screen_update(self):
        self.apply("screen-metrics")

    def update_children(self):
        if not self.stopped and not self.applying:
            self.applying = True
            try:
                metrics(self.window, self.state.scale_factor)
            finally:
                self.applying = False

    def bind_screen(self, screen):
        if screen is self.screen:
            return
        if self.screen is not None and isValid(self.screen):
            for signal in (self.screen.logicalDotsPerInchChanged, self.screen.geometryChanged,
                           self.screen.availableGeometryChanged):
                signal.disconnect(self.schedule_screen_update)
        self.screen = screen
        if screen is not None:
            for signal in (screen.logicalDotsPerInchChanged, screen.geometryChanged,
                           screen.availableGeometryChanged):
                signal.connect(self.schedule_screen_update)

    def manual_change(self, *args):
        self.window.settings.data["ui_scale_delta_percent"] = self.window.system_tab.scale_combo.currentData()
        self.apply("manual-delta")

    def apply(self, reason="runtime"):
        if self.stopped or self.applying:
            return
        window = self.window
        screen = window.screen() or self.application.primaryScreen()
        self.bind_screen(screen)
        state = resolve_screen(screen, window.settings.data["ui_scale_delta_percent"])
        old = self.state.scale_factor if self.state else 1.0
        changed = self.state != state
        self.state = state
        self.applying = True
        try:
            metrics(window, 1.0, capture_only=True)
            if changed:
                apply_theme(self.application, scale_factor=state.scale_factor)
                self.application.setStyleSheet(self.application.styleSheet() + appendix(state.scale_factor))
            metrics(window, state.scale_factor)
            window.settings.data.update(ui_scale_mode="auto", ui_scale_delta_percent=state.delta_percent,
                                        ui_scale_percent=state.final_percent)
            window.settings.save()
            if reason in ("startup", "manual-delta") and not window.isMaximized() and screen is not None:
                area = screen.availableGeometry()
                hint = window.minimumSizeHint().expandedTo(window.minimumSize())
                ratio = state.scale_factor / old if reason == "manual-delta" else 1.0
                width, height = target_window_size(window.width(), window.height(), ratio,
                                                  hint.width(), hint.height(), area.width(), area.height())
                window.resize(width, height)
                rect = window.geometry()
                if not area.contains(rect):
                    rect.moveCenter(area.center())
                    window.move(rect.topLeft())
                window.save_geometry()
        finally:
            self.applying = False

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.timer.stop()
        self.metrics_timer.stop()
        self.application.removeEventFilter(self)
        self.bind_screen(None)
        for signal in (self.application.primaryScreenChanged, self.application.screenAdded,
                       self.application.screenRemoved):
            signal.disconnect(self.schedule_screen_update)
        if self.handle is not None and isValid(self.handle):
            self.handle.screenChanged.disconnect(self.schedule_screen_update)
        apply_theme(self.application)
        self.application.setStyleSheet(self.application.styleSheet() + appendix())
