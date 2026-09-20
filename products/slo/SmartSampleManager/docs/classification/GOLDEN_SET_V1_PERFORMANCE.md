# SLO Scanning Performance Baseline

Statistical timing and memory metrics collected over repeated runs against the 170-file golden corpus:

## Repeated-Run Scan Timing
- **Cold Scan Mean Time**: 25043.20 ms (25.04 seconds total)
- **Cold Scan Standard Deviation**: 1108.74 ms
- **Cached Scan Mean Time**: 921.50 ms (0.92 seconds total)
- **Scanning Throughput (Cold)**: 6.8 files/second
- **Scanning Throughput (Cached)**: 184.5 files/second

## Resident Memory Usage (RSS)
- **Baseline Memory (Idle)**: 14.28 MB
- **Peak Scanning Memory**: 2439.41 MB
- **Retained Memory (Post Scan)**: 1359.55 MB
