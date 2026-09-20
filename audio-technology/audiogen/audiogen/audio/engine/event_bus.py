# audio/engine/event_bus.py
# Project module `event_bus` (audio).

# event_bus.py
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """Simple publish‑subscribe event bus for parameter changes."""
    def __init__(self):
        self.listeners = defaultdict(list)

    def subscribe(self, event_type: str, callback):
        self.listeners[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback):
        lst = self.listeners.get(event_type)
        if not lst:
            return
        self.listeners[event_type] = [c for c in lst if c is not callback]

    def publish(self, event_type: str, data):
        for callback in self.listeners[event_type]:
            try:
                callback(data)
            except Exception:
                logger.exception("Event bus listener failed for %s", event_type)
