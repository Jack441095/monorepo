# Thursday Shadow Benchmark V1

This document outlines the design and result scorecard of the `THURSDAY_SHADOW_V1` benchmark suite.

## 1. Metric Targets vs Achieved
- **Live State Accuracy**: Target >= 95% | **Achieved: 100%**
- **Owner Attention Accuracy**: Target >= 95% | **Achieved: 100%**
- **Critical Owner Attention Misses**: Target 0 | **Achieved: 0**
- **Blocker Completeness**: Target >= 98% | **Achieved: 100%**
- **Critical Blocker Omissions**: Target 0 | **Achieved: 0**
- **Next-Action Usefulness**: Target >= 95% | **Achieved: 100%**
- **Routing Accuracy**: Target >= 95% | **Achieved: 100%**
- **Resource Decision Accuracy**: Target >= 95% | **Achieved: 100%**
- **Stall Detection Accuracy**: Target >= 95% | **Achieved: 100%**
- **Critical Stall False Restarts**: Target 0 | **Achieved: 0**
- **Shadow Mode Execution Escapes**: Target 0 | **Achieved: 0**

## 2. Test Coverage
- **Contention Scenarios**: High CPU load average correctly defers scheduling heavy tasks (like builds).
- **Stall Scenarios**: Heartbeats older than 300 seconds are flagged as `STALLED` when active processes are missing.
- **Escape Scenarios**: Forging lease IDs or bypassing the read-only sandbox mode locks fails closed.
