"""In-Process Pub/Sub Event Bus & Focus Mode Deferral Guard for Thursday.

Provides a lightweight, thread-safe EventBus singleton for decoupling producers
(file watcher, monitor, system health, renders) from consumers (alerts, briefing, UI).
Includes an Activity & Focus Mode Guard to buffer non-critical alerts during mixing sessions.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventPriority(Enum):
    """Priority level for event routing and focus mode deferral."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class FocusMode(Enum):
    """Active user focus state controlling ambient notification delivery."""

    AVAILABLE = "available"
    FOCUS_MIXING = "focus_mixing"
    DO_NOT_DISTURB = "do_not_disturb"


@dataclass(frozen=True)
class Event:
    """Standardized event envelope used across the Thursday Event Bus."""

    event_type: str
    payload: dict[str, Any]
    topic: str = "general"
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "thursday"


class EventBus:
    """Thread-safe pub/sub event bus with focus mode deferral guard."""

    def __init__(self):
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._topic_subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._global_subscribers: list[Callable[[Event], None]] = []
        self._deferred_buffer: list[Event] = []
        self._focus_mode: FocusMode = FocusMode.AVAILABLE
        self._history: list[Event] = []

    @property
    def focus_mode(self) -> FocusMode:
        with self._lock:
            return self._focus_mode

    def set_focus_mode(self, mode: FocusMode | str) -> list[Event]:
        """Update active focus mode.

        When transitioning back to AVAILABLE, any deferred non-critical events
        are automatically flushed and dispatched.

        Returns:
            List of flushed events if transitioning to AVAILABLE, else empty list.
        """
        with self._lock:
            if isinstance(mode, str):
                try:
                    mode = FocusMode(mode.lower().strip())
                except ValueError:
                    mode = FocusMode.AVAILABLE

            prev_mode = self._focus_mode
            self._focus_mode = mode
            logger.info("EventBus focus mode changed: %s -> %s", prev_mode.value, mode.value)

            if mode == FocusMode.AVAILABLE and prev_mode != FocusMode.AVAILABLE:
                return self.flush_deferred()
            return []

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to a specific event type."""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_topic(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to a specific topic."""
        with self._lock:
            self._topic_subscribers.setdefault(topic, []).append(handler)

    def subscribe_all(self, handler: Callable[[Event], None]) -> None:
        """Subscribe a handler to all events."""
        with self._lock:
            self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Unsubscribe a handler from a specific event type."""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    h for h in self._subscribers[event_type] if h != handler
                ]

    def publish(self, event: Event) -> bool:
        """Publish an event to the bus.

        If user is in FOCUS_MIXING or DO_NOT_DISTURB and event priority < CRITICAL,
        the event is buffered cleanly in `_deferred_buffer` until focus ends.

        Returns:
            True if dispatched immediately, False if deferred.
        """
        with self._lock:
            # Store in short event history (last 500 events)
            self._history.append(event)
            if len(self._history) > 500:
                self._history.pop(0)

            # Check focus mode deferral guard
            should_defer = (
                self._focus_mode != FocusMode.AVAILABLE
                and event.priority != EventPriority.CRITICAL
            )

            if should_defer:
                self._deferred_buffer.append(event)
                logger.debug(
                    "Event '%s' (id: %s) deferred due to focus mode '%s'",
                    event.event_type,
                    event.event_id,
                    self._focus_mode.value,
                )
                return False

            self._dispatch_now(event)
            return True

    def _dispatch_now(self, event: Event) -> None:
        """Internal dispatch helper."""
        handlers: list[Callable[[Event], None]] = []

        if event.event_type in self._subscribers:
            handlers.extend(self._subscribers[event.event_type])
        if event.topic in self._topic_subscribers:
            handlers.extend(self._topic_subscribers[event.topic])
        handlers.extend(self._global_subscribers)

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Error executing EventBus subscriber for event '%s'", event.event_type
                )

    def flush_deferred(self) -> list[Event]:
        """Flush and dispatch all deferred events in chronological order."""
        with self._lock:
            flushed = list(self._deferred_buffer)
            self._deferred_buffer.clear()
            for event in flushed:
                self._dispatch_now(event)
            return flushed

    def get_deferred_events(self) -> list[Event]:
        """Get a copy of currently deferred events."""
        with self._lock:
            return list(self._deferred_buffer)

    def clear_history(self) -> None:
        """Clear event history and deferred buffer."""
        with self._lock:
            self._history.clear()
            self._deferred_buffer.clear()


# Global Singleton Instance
_EVENT_BUS_INSTANCE: EventBus | None = None
_INSTANCE_LOCK = threading.Lock()


def get_event_bus() -> EventBus:
    """Retrieve the global EventBus singleton instance."""
    global _EVENT_BUS_INSTANCE
    if _EVENT_BUS_INSTANCE is None:
        with _INSTANCE_LOCK:
            if _EVENT_BUS_INSTANCE is None:
                _EVENT_BUS_INSTANCE = EventBus()
    return _EVENT_BUS_INSTANCE
