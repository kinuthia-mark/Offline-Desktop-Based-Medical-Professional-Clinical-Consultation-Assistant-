"""Run slow work (speech-to-text, drafting, unlocking) away from the screen's own thread.

Qt draws the window on one thread. If a 2-minute transcription ran there, the window would
freeze and Windows would offer to close it. `run_in_background` runs the function on a worker
thread and calls `on_done` or `on_error` back on the screen's thread, where it is safe to update
widgets.
"""

# This file lets the other screens run slow work without freezing the window. Qt signals carry
# the result back to the screen thread, the only thread allowed to change widgets.
from __future__ import annotations

from collections.abc import Callable

# QRunnable is a job for the thread pool; Signal is Qt's way to send a result across threads.
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


# A QRunnable cannot send signals itself, so this small object does it for the job.
class _Signals(QObject):
    # done carries the result; failed carries the error.
    done = Signal(object)
    failed = Signal(object)


# One unit of background work. It wraps a function with no arguments.
class _Job(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    # Qt's thread pool calls run() on a worker thread.
    def run(self) -> None:
        try:
            result = self.fn()
        except Exception as exc:  # handed to the screen, which shows the error's code
            # Send the error as a signal. The screen shows only its short code.
            self.signals.failed.emit(exc)
        else:
            # No error: send the result.
            self.signals.done.emit(result)


# The set stops Python deleting a job before its signals arrive.
_KEEP: set[_Job] = set()  # keep each job alive until its signals have been delivered


# Start fn on a worker thread. on_done or on_error is then called on the screen's thread.
def run_in_background(
    fn: Callable[[], object],
    on_done: Callable[[object], None],
    on_error: Callable[[Exception], None],
) -> None:
    job = _Job(fn)
    _KEEP.add(job)

    # Free the job, then call the screen's function.
    def finish(callback, value) -> None:
        _KEEP.discard(job)
        callback(value)

    # Connect the signals. The lambdas pass the right callback to finish().
    job.signals.done.connect(lambda result: finish(on_done, result))
    job.signals.failed.connect(lambda exc: finish(on_error, exc))
    # The global pool picks a free thread and runs the job.
    QThreadPool.globalInstance().start(job)


# Turn an error into a short code that the screen turns into a plain message.
def error_code(exc: Exception) -> str:
    """The short code carried by our own errors; never the text of anything else."""
    # Imported here to avoid a circular import.
    from clinassist.domain import WorkflowError

    if isinstance(exc, WorkflowError):
        return str(exc)  # workflow errors are raised with the code as their only text
    # Fall back from 'code' to 'reason' to a general code, so the screen never shows raw error text.
    return getattr(exc, "code", None) or getattr(exc, "reason", None) or "unexpected_error"
