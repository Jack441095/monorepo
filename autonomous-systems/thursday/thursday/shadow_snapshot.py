"""Canonical Live Company Snapshot V2 for Thursday V2-E."""

from __future__ import annotations

import os
import psutil
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

class ProgrammeStatus:
    NOT_STARTED = "NOT_STARTED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    PASS = "PASS"
    FAIL = "FAIL"
    QUALIFIED = "QUALIFIED"
    INTEGRATION_READY = "INTEGRATION_READY"
    OWNER_ACTION_REQUIRED = "OWNER_ACTION_REQUIRED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"

class FreshnessClass:
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"

@dataclass
class ProgrammeEntity:
    project_id: str
    display_name: str
    branch: str = "UNKNOWN"
    head_sha: str = "UNKNOWN"
    cleanliness: bool = True
    status: str = ProgrammeStatus.UNKNOWN
    observed_at: float = field(default_factory=time.time)
    source_timestamp: float = 0.0
    latest_report_summary: str = ""
    blockers: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    owner_action_required: bool = False
    resource_class: str = "LIGHT"  # HEAVY, MEDIUM, LIGHT

    def get_freshness(self, now: float) -> str:
        age = now - self.observed_at
        if age < 60:
            return FreshnessClass.FRESH
        elif age < 300:
            return FreshnessClass.AGING
        return FreshnessClass.STALE

@dataclass
class HostSystemMetrics:
    cpu_percent: float
    memory_percent: float
    load_avg: tuple[float, float, float]
    heavy_running_count: int = 0

@dataclass
class CompanySnapshotV2:
    captured_at_epoch: float = field(default_factory=time.time)
    programmes: dict[str, ProgrammeEntity] = field(default_factory=dict)
    metrics: HostSystemMetrics = field(default_factory=lambda: HostSystemMetrics(0.0, 0.0, (0.0, 0.0, 0.0)))

    def is_heavy_load(self) -> bool:
        return self.metrics.cpu_percent > 85.0 or self.metrics.heavy_running_count >= 2

def collect_host_metrics(heavy_processes_keywords: list[str]) -> HostSystemMetrics:
    """Safely sample system CPU, RAM and count heavy C++ builds / ML runs (read-only)."""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    
    # Count heavy builds/processes matching keywords
    heavy_count = 0
    for p in psutil.process_iter(attrs=["name", "cmdline"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if any(kw in cmd for kw in heavy_processes_keywords):
                heavy_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    return HostSystemMetrics(cpu_percent=cpu, memory_percent=mem, load_avg=load, heavy_running_count=heavy_count)
