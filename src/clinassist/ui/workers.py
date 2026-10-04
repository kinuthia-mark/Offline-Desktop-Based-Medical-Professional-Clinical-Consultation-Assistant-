"""Run slow work (speech-to-text, drafting, unlocking) away from the screen's own thread.

Qt draws the window on one thread. If a 2-minute transcription ran there, the window would
freeze and Windows would offer to close it. `run_in_background` runs the function on a worker
thread and calls `on_done` or `on_error` back on the screen's thread, where it is safe to update
widgets.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # handed to the screen, which shows the error's code
            self.signals.failed.emit(exc)
        else:
            self.signals.done.emit(result)


_KEEP: set[_Job] = set()  # keep each job alive until its signals have been delivered


def run_in_background(
    fn: Callable[[], object],
    on_done: Callable[[object], None],
    on_error: Callable[[Exception], None],
) -> None:
    job = _Job(fn)
    _KEEP.add(job)

    def finish(callback, value) -> None:
        _KEEP.discard(job)
        callback(value)

    job.signals.done.connect(lambda result: finish(on_done, result))
    job.signals.failed.connect(lambda exc: finish(on_error, exc))
    QThreadPool.globalInstance().start(job)


def error_code(exc: Exception) -> str:
    """The short code carried by our own errors; never the text of anything else."""
    from clinassist.domain import WorkflowError

    if isinstance(exc, WorkflowError):
        return str(exc)  # workflow errors are raised with the code as their only text
    return getattr(exc, "code", None) or getattr(exc, "reason", None) or "unexpected_error"
