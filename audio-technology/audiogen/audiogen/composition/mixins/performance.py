# composition/mixins/performance.py
# Project module `performance` (composition).

# performance.py
import logging
import time
from collections import defaultdict
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """Simple performance monitoring utility"""
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.timings = defaultdict(list)
    
    @contextmanager
    def measure(self, name: str):
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.timings[name].append(elapsed)
    
    def report(self, threshold: float = 0.01):
        if not self.enabled or not self.timings:
            return
        logger.info("[PERFORMANCE] Average timings:")
        for name, times in self.timings.items():
            if len(times) > 0:
                avg = sum(times) / len(times)
                if avg > threshold:
                    logger.info("  %s: %.2fms (calls: %d)", name, avg * 1000, len(times))
    
    def reset(self):
        self.timings.clear()


class PerformanceMixin:
    """Adds performance monitoring to CompositionGenerator"""
    def __init__(self, *args, **kwargs):
        # No super() call – we initialize our own attribute
        self.perf_monitor = PerformanceMonitor(enabled=kwargs.get('enable_perf_monitoring', False))
