from typing import Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class BackgroundTask(QRunnable):
    """Runs `fn` on the thread pool; its result or error message comes back as a signal on the UI thread."""

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as e:  # any collector failure must reach the UI, not kill the thread
            self.signals.failed.emit(str(e))
        else:
            self.signals.done.emit(result)
