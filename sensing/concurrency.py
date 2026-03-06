"""Reusable threading primitives for periodic background tasks."""

import contextlib
import threading
from collections.abc import Callable
from types import TracebackType

__all__ = ["RepeatingTask"]


class RepeatingTask(contextlib.AbstractContextManager["RepeatingTask"]):
    """Context manager that calls a callable once immediately then at a fixed interval.

    Owns a daemon ``threading.Thread`` and a ``threading.Event`` for
    cancellation. Uses ``Event.wait()`` so the thread wakes instantly on
    cancel rather than blocking for a full interval.

    Args:
        task: Zero-argument callable called once on entry then per interval.
        interval: Seconds between consecutive calls after the first.
    """

    def __init__(self, task: Callable[[], None], interval: float) -> None:
        """Store task and interval; thread is not started until ``__enter__``.

        Raises:
            ValueError: If ``interval`` is not positive.
        """
        if interval <= 0:
            raise ValueError(f"interval must be positive, got {interval!r}")
        self._task = task
        self._interval = interval
        self._cancel = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def __enter__(self) -> "RepeatingTask":
        """Start the background thread."""
        self._cancel.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cancel the background thread and block until it exits."""
        self._cancel.set()
        self._thread.join()

    def _loop(self) -> None:
        """Call the task immediately, then repeat until cancel is set."""
        self._task()
        while not self._cancel.wait(self._interval):
            self._task()
