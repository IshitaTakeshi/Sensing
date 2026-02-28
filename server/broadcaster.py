"""Manages active WebSocket subscriber queues and message broadcasting."""

import asyncio

__all__ = ["add_subscriber", "broadcast_message", "remove_subscriber"]

_subscriber_queues: list[asyncio.Queue[str]] = []


def add_subscriber(queue: asyncio.Queue[str]) -> None:
    """Add a new subscriber queue to the global broadcast list."""
    _subscriber_queues.append(queue)


def remove_subscriber(queue: asyncio.Queue[str]) -> None:
    """Remove a subscriber queue from the global broadcast list."""
    _subscriber_queues.remove(queue)


def _enqueue_message(queue: asyncio.Queue[str], message: str) -> None:
    if queue.full():
        queue.get_nowait()
    queue.put_nowait(message)


def broadcast_message(message: str, loop: asyncio.AbstractEventLoop) -> None:
    """Dispatch a message to all active subscriber queues safely."""
    for queue in list(_subscriber_queues):
        loop.call_soon_threadsafe(_enqueue_message, queue, message)
