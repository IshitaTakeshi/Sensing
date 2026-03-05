"""Tests for RepeatingTask."""

import threading

from sensing.concurrency import RepeatingTask


class TestRepeatingTask:
    def test_calls_task_immediately_on_enter(self):
        called = threading.Event()
        with RepeatingTask(called.set, interval=60.0):
            assert called.wait(timeout=1.0)

    def test_calls_task_again_after_interval(self):
        calls: list[int] = []
        done = threading.Event()

        def task() -> None:
            calls.append(1)
            if len(calls) >= 2:
                done.set()

        with RepeatingTask(task, interval=0.0):
            assert done.wait(timeout=1.0)
        assert len(calls) >= 2

    def test_exit_stops_task_promptly(self):
        calls: list[int] = []
        started = threading.Event()

        def task() -> None:
            calls.append(1)
            started.set()

        with RepeatingTask(task, interval=60.0):
            assert started.wait(timeout=1.0)
        count_at_exit = len(calls)
        assert count_at_exit >= 1
        # After exit, the thread is joined -- no further calls can happen.
        assert len(calls) == count_at_exit

    def test_context_manager_is_reentrant(self):
        calls: list[int] = []
        first = threading.Event()
        second = threading.Event()

        def task() -> None:
            calls.append(1)
            if len(calls) == 1:
                first.set()
            if len(calls) == 2:
                second.set()

        rt = RepeatingTask(task, interval=60.0)
        with rt:
            assert first.wait(timeout=1.0)
        with rt:
            assert second.wait(timeout=1.0)
        assert len(calls) >= 2
