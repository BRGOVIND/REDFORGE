# Phase 1 size and runtime measurements

Measured on the Windows development machine on 2026-10-21. Baseline: clean `a8ed6c3` at RedForge 2.0.4. Current: Phase 1 working tree. These are development build measurements, not claims about other platforms.

| Artifact | Baseline | Phase 1 | Change |
| --- | ---: | ---: | ---: |
| Frontend HTML/CSS/JS, raw | 1,099,827 B | 1,110,757 B | +10,930 B |
| Frontend HTML/CSS/JS, per-file gzip level 9 | 335,615 B | 338,630 B | +3,015 B |
| Full `frontend/dist`, raw | 1,300,891 B | 1,311,821 B | +10,930 B |
| Full `frontend/dist`, per-file gzip level 9 | 534,435 B | 537,279 B | +2,844 B |

Trace Explorer and detail are lazy chunks: 10,222 B raw and 3,853 B gzip together. They are not loaded by the dashboard route. SDK adds 13,884 B Python source, 4,012 B gzip, and zero mandatory third-party dependencies. SQL tables and indexes add storage only when traces are collected.

Hot-path microbenchmark: Python 3.12, 20,000 empty calls per run, five runs, median. Plain call: 0.017 µs. Metadata-only `Tracer.observe` with delivery callback stubbed: 4.655 µs. Incremental overhead: 4.638 µs/call. `tracemalloc` peak during 1,000 sequential observed calls: 10,056 B. This measures instrumentation work, not provider/network latency or production memory under concurrent traffic. Delivery uses a bounded 256-event queue and separate daemon thread, so model calls do not wait for RedForge.

The existing local Windows v2.0.4 Setup executable is 152,834,887 B. It predates Phase 1. A new PyInstaller/Electron installer has **not** been built, so exact installed-app delta and startup/memory changes are **not yet measured**; do not compare the old executable against the new source bundle as if they were equivalent. Before release, run the desktop packaging pipeline on a clean builder and record the new installer size, startup time, idle memory, and an ingestion throughput sample. Do not remove PyInstaller dependencies solely from size guesses: validate any exclusion against offline workflows first.
