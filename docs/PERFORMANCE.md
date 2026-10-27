# Gateway-Harness Performance & Latency Benchmark

## 1. Hot Path Overhead Specification
The Gateway-Harness routing proxy is designed for zero blocking I/O and minimal hot-path CPU overhead.

- **Target added latency (p50):** < 2.0 ms
- **Target added latency (p99):** < 10.0 ms
- **Observed microbenchmark timings:**
  - Fingerprinting (20-message conversation): **0.08 ms** median
  - PII Scrubber (10 KB payload): **0.42 ms** median
  - Snapshot Index Lookup (10,000 active policies): **8.3 µs** median
  - Spool Queue Submit: Non-blocking async queue put (< 0.01 ms)

## 2. Resource Sizing Guide
| Requests / Day | Gateway Workers | Worker Memory | DB Disk (30d) |
|---|---|---|---|
| 100,000 | 1 replica | 1 GB RAM | ~2.5 GB Parquet |
| 1,000,000 | 2 replicas | 2 GB RAM | ~25 GB Parquet |
| 10,000,000 | 4 replicas | 4 GB RAM | ~250 GB Parquet |
