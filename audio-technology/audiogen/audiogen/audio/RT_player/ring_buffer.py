# audio/RT_player/ring_buffer.py
# Project module `ring_buffer` (audio).

import threading
import time
from collections import deque
from typing import Optional


class RingBuffer:
    """Thread-safe FIFO queue with capacity; optional blocking write with Condition wakeups."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
        self._cond = threading.Condition()

    def write(self, item) -> bool:
        with self._cond:
            if len(self.buffer) >= self.capacity:
                return False
            self.buffer.append(item)
            return True

    def write_blocking(self, item, timeout: Optional[float] = None) -> bool:
        """
        Block until a slot is available (or ``timeout`` seconds elapse).

        Returns True if ``item`` was queued. On timeout while full, returns False.
        If ``timeout`` is None, wait indefinitely.
        """
        with self._cond:
            if timeout is None:
                while len(self.buffer) >= self.capacity:
                    self._cond.wait()
            else:
                deadline = time.monotonic() + max(0.0, float(timeout))
                while len(self.buffer) >= self.capacity:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._cond.wait(timeout=remaining)
            self.buffer.append(item)
            return True

    def read(self):
        with self._cond:
            if not self.buffer:
                return None
            item = self.buffer.popleft()
            self._cond.notify()
            return item

    def __len__(self):
        with self._cond:
            return len(self.buffer)

    def clear(self):
        with self._cond:
            had = len(self.buffer) > 0
            self.buffer.clear()
            if had:
                self._cond.notify_all()

    def trim_to(self, max_items: int) -> int:
        max_items = max(0, int(max_items))
        removed = 0
        with self._cond:
            while len(self.buffer) > max_items:
                self.buffer.pop()
                removed += 1
            if removed:
                self._cond.notify_all()
        return removed
