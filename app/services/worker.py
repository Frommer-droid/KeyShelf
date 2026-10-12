from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    done = Signal(object, str)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self):
        try:
            result = self.function()
            self.signals.done.emit(result, "")
        except Exception as error:
            from app.services.autostart import AutostartError
            from app.services.exchange import ExchangeError
            from app.services.vault import VaultError
            # Текст системного исключения может включать пользовательские данные.
            message = str(error) if isinstance(error, (VaultError, ExchangeError, AutostartError)) else "Операция не выполнена. Проверьте доступ к файлу и свободное место."
            self.signals.done.emit(None, message)
        finally:
            self.function = None
